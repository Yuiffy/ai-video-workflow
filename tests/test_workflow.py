import json
import subprocess
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import httpx
from filelock import FileLock, Timeout
from pydantic import ValidationError

from src.cli import load_config, main
from src.jimeng_cli import JimengCli
from src.models import Project, Scene
from src.storage import read_json, write_json
from src.voice_service import create_server


def response(data, code=0):
    return subprocess.CompletedProcess([], code, json.dumps(data), "")


def wav(path):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)


class DreaminaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.client = JimengCli({"executable": "dreamina"})

    def test_resume_after_network_failure_does_not_submit_twice(self):
        submitted = {"submit_id": "known-id", "gen_status": "querying"}
        with patch("src.jimeng_cli.subprocess.run", side_effect=[
                response(submitted), subprocess.TimeoutExpired("query_result", 1)]) as call:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.client.run("hello", self.out, "s")
            self.assertEqual(call.call_count, 2)
        self.assertEqual(read_json(self.out/"job.json")["submit_id"], "known-id")
        with patch("src.jimeng_cli.subprocess.run", return_value=response(submitted)) as call:
            self.client.run("hello", self.out, "s")
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[0][1], "query_result")

    def test_uncertain_submit_never_retries(self):
        with patch("src.jimeng_cli.subprocess.run", side_effect=subprocess.TimeoutExpired("submit", 1)):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.client.run("hello", self.out, "s")
        with patch("src.jimeng_cli.subprocess.run") as call:
            with self.assertRaisesRegex(RuntimeError, "unknown"):
                self.client.run("hello", self.out, "s")
            call.assert_not_called()

    def test_missing_submit_id_keeps_reservation(self):
        with patch("src.jimeng_cli.subprocess.run", return_value=response({"error": "maybe submitted"})):
            with self.assertRaises(RuntimeError):
                self.client.run("hello", self.out, "s")
        with patch("src.jimeng_cli.subprocess.run") as call:
            with self.assertRaises(RuntimeError):
                self.client.run("hello", self.out, "s")
            call.assert_not_called()

    def test_query_success_without_download_is_not_ready(self):
        write_json(self.out/"job.json", {"submit_id": "known-id"})
        with patch("src.jimeng_cli.subprocess.run", return_value=response({
                "submit_id": "known-id", "gen_status": "success",
                "result_json": {"videos": [{"path": str(self.out/"missing.mp4")}]}})):
            self.assertFalse(self.client.query(self.out)["downloaded"])

    def test_changed_prompt_rejects_new_charge(self):
        with patch("src.jimeng_cli.subprocess.run", return_value=response({
                "submit_id": "known-id", "gen_status": "querying"})):
            self.client.run("first", self.out, "s")
        with patch("src.jimeng_cli.subprocess.run") as call:
            with self.assertRaisesRegex(RuntimeError, "another request"):
                self.client.run("different", self.out, "s")
            call.assert_not_called()

    def test_audio_reference_is_forwarded_with_image(self):
        client = JimengCli({"images": ["image.png"]})
        plan = client.plan("reference @Audio 1", self.out, "s", 12, "voice.wav")
        cmd = plan["command"]
        self.assertEqual(cmd[1], "multimodal2video")
        self.assertEqual(cmd[cmd.index("--audio")+1], "voice.wav")
        self.assertEqual(cmd[cmd.index("--duration")+1], "12")

    def test_audio_only_rejected_before_spending(self):
        with self.assertRaisesRegex(ValueError, "require an image"):
            self.client.plan("hello", self.out, "s", 10, "voice.wav")

    def test_other_model_rejected(self):
        with self.assertRaises(ValueError):
            JimengCli({"model": "seedance2.5"}).plan("hi", self.out, "s")

    def test_second_writer_is_blocked(self):
        with FileLock(str(self.out/"job.lock")):
            with patch("src.jimeng_cli.subprocess.run") as call:
                with self.assertRaises(Timeout):
                    self.client.run("hello", self.out, "s")
                call.assert_not_called()

    def test_adopt_wrong_prompt_does_not_change_selection(self):
        write_json(self.out/"job.json", {"submit_id": "original"})
        with patch("src.jimeng_cli.subprocess.run", return_value=response({
                "submit_id": "candidate", "prompt": "wrong"})):
            with self.assertRaises(ValueError):
                self.client.adopt(self.out, "candidate", "wanted", "s")
        self.assertEqual(read_json(self.out/"job.json")["submit_id"], "original")


class ContractTests(unittest.TestCase):
    def test_unsafe_scene_names_rejected(self):
        with self.assertRaises(ValidationError):
            Scene(id="../elsewhere", title="t", narration="n", visual="v")

    def test_duplicate_scene_names_rejected(self):
        scene = {"id": "a", "title": "t", "narration": "n", "visual": "v"}
        with self.assertRaises(ValidationError):
            Project(id="p", title="t", script="s", ppt="p", scenes=[scene, scene])

    def test_all_execution_commands_honor_dry_run(self):
        project = Path(__file__).resolve().parents[1]/"projects/development-history/project.json"
        with tempfile.TemporaryDirectory() as directory:
            cfg = load_config(Path(__file__).resolve().parents[1]/"config.example.json")
            cfg["output_dir"] = directory
            config = Path(directory)/"test-config.json"
            write_json(config, cfg)
            for command in ("run", "voice", "jimeng", "poll", "render", "record"):
                with patch("sys.argv", ["cli", command, str(project), "--config", str(config), "--dry-run"]):
                    with patch("src.jimeng_cli.subprocess.run") as provider:
                        self.assertEqual(main(), 0)
                        provider.assert_not_called()


class VoiceServiceTests(unittest.TestCase):
    def test_local_service_transports_real_wav_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"source.wav"
            wav(source)
            with patch("src.voice_service.RvcClient") as factory:
                factory.return_value.tts.side_effect = lambda text, target, speed: target.write_bytes(source.read_bytes())
                factory.return_value.convert.side_effect = lambda inp, target, pitch: target.write_bytes(inp.read_bytes())
                server = create_server({"model": "test"}, 0)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False) as client:
                        self.assertEqual(client.get("/health").json()["status"], "ready")
                        result = client.post("/api/tts", json={"text": "你好", "speed": 1})
                        self.assertEqual(result.content, source.read_bytes())
                        self.assertEqual(result.headers["content-type"], "audio/wav")
                        self.assertEqual(client.post("/api/tts", json={"text": ""}).status_code, 400)
                finally:
                    server.shutdown()
                    server.server_close()
                    worker.join()


if __name__ == "__main__":
    unittest.main()
