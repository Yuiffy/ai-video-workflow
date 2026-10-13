import io
import json
import os
import re
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import httpx

from src.tts import (DEFAULTS, SpeechError, api_key, load_settings, minimax_request,
                     public_settings, save_settings, synthesize)
from src.voice_studio import create_server
from src.models import Scene
from src.voice import produce_voice


def sample_wav():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x01\x00" * 1600)
    return stream.getvalue()


class VoiceStudioTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "settings.json"

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_key_encrypted_and_never_returned(self):
        with patch.dict(os.environ, {}, clear=True):
            result = save_settings({"api_key": "test-secret-not-real"}, self.path)
            self.assertTrue(result["has_key"])
            self.assertNotIn("test-secret-not-real", self.path.read_text())
            self.assertNotIn("api_key_dpapi", result)
            self.assertEqual(api_key(load_settings(self.path)), "test-secret-not-real")
            save_settings({"api_key": "", "voice_id": "chosen"}, self.path)
            self.assertEqual(api_key(load_settings(self.path)), "test-secret-not-real")

    def test_minimax_does_not_retry_uncertain_paid_request(self):
        with patch("src.tts.api_key", return_value="test"), patch("src.tts.httpx.Client") as client:
            post = client.return_value.__enter__.return_value.post
            post.side_effect = httpx.ReadTimeout("provider might have processed request")
            with self.assertRaises(SpeechError):
                minimax_request("t2a_v2", {}, DEFAULTS)
            self.assertEqual(post.call_count, 1)

    def test_cloud_wav_and_voice_selection(self):
        target = Path(self.directory.name) / "voice.wav"
        data = {"data": {"audio": sample_wav().hex()}, "extra_info": {"usage_characters": 4}}
        with patch("src.tts.minimax_request", return_value=data) as request:
            synthesize("你好", target, {**DEFAULTS, "provider": "minimax", "voice_id": "my-clone", "emotion": "calm"})
        self.assertEqual(target.read_bytes(), sample_wav())
        payload = request.call_args.args[1]
        self.assertEqual(payload["voice_setting"]["voice_id"], "my-clone")
        self.assertEqual(payload["audio_setting"]["format"], "wav")

    def test_provider_error_does_not_echo_sensitive_response(self):
        with patch("src.tts.api_key", return_value="test"), patch("src.tts.httpx.Client") as client:
            post = client.return_value.__enter__.return_value.post
            post.return_value = httpx.Response(200, json={"base_resp": {"status_code": 1004, "status_msg": "secret-value"}})
            with self.assertRaises(SpeechError) as caught:
                minimax_request("get_voice", {}, DEFAULTS)
            self.assertNotIn("secret-value", str(caught.exception))

    def test_direct_tts_skips_rvc_and_caches_complete_scene(self):
        save_settings({"provider": "minimax", "voice_id": "clone"}, self.path)
        scene = Scene(id="demo", title="demo", visual="demo", narration="第一句，接着说完这一句。")
        config = {"rvc": {}, "tts": {"settings_path": str(self.path)}}
        def generate(text, target, settings):
            target.write_bytes(sample_wav())
        def normalize(ffmpeg, source, target):
            target.write_bytes(source.read_bytes())
        with patch("src.tts.synthesize", side_effect=generate) as tts, \
                patch("src.voice.normalize_audio", side_effect=normalize), \
                patch("src.voice.duration", return_value=0.1), \
                patch("src.voice.RvcClient.convert") as convert:
            produce_voice(scene, Path(self.directory.name), config)
            produce_voice(scene, Path(self.directory.name), config)
            tts.assert_called_once()
            self.assertEqual(tts.call_args.args[0], scene.narration)
            convert.assert_not_called()
            save_settings({"voice_id": "another-clone"}, self.path)
            produce_voice(scene, Path(self.directory.name), config)
            self.assertEqual(tts.call_count, 2)
        metadata = json.loads((Path(self.directory.name) / "voice/demo.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["caption_timing"], "authored-proportional")

    def test_loopback_host_csrf_and_no_secret_api(self):
        server = create_server(self.path, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False) as client:
                page = client.get("/")
                self.assertEqual(page.status_code, 200)
                token = re.search(r'name="studio-token" content="([^"]+)"', page.text)[1]
                self.assertEqual(client.post("/api/settings", json={"voice_id": "x"}).status_code, 403)
                headers = {"X-Studio-Token": token, "Origin": "https://example.org"}
                self.assertEqual(client.post("/api/settings", json={"voice_id": "x"}, headers=headers).status_code, 403)
                self.assertEqual(client.get("/api/settings", headers={"Host": "evil.example"}).status_code, 403)
                headers.pop("Origin")
                self.assertEqual(client.post("/api/settings", json={"voice_id": "x"}, headers=headers).status_code, 200)
                data = client.get("/api/settings").json()
                self.assertEqual(data["voice_id"], "x")
                self.assertNotIn("api_key_dpapi", data)
                self.assertEqual(client.get("/settings.json").status_code, 404)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_cosy_uses_own_reference_and_requires_transcript(self):
        root = Path(self.directory.name)
        runtime = root / '.venv/Scripts/python.exe'
        runtime.parent.mkdir(parents=True)
        runtime.touch()
        reference = root / 'daily.wav'
        reference.write_bytes(sample_wav())
        target = root / 'generated.wav'
        settings = {**DEFAULTS, 'cosy_root': str(root),
                    'cosy_reference_audio': str(reference), 'reference_audio': 'unused.wav'}
        with patch('src.tts.subprocess.run') as run, patch('src.tts.minimax_request') as cloud:
            with self.assertRaisesRegex(SpeechError, '对应的文字'):
                synthesize('测试', target, settings)
            run.assert_not_called()
            settings['cosy_reference_text'] = '参考原文。'
            def worker(command, **kwargs):
                self.assertEqual(Path(command[1]).name, 'cosy_tts_worker.py')
                request = json.loads(Path(command[-1]).read_text(encoding='utf-8'))
                self.assertEqual(request['reference'], str(reference.resolve()))
                self.assertEqual(request['reference_text'], '参考原文。')
                self.assertIs(request['text_frontend'], settings['cosy_text_frontend'])
                target.write_bytes(sample_wav())
                return type('Result', (), {'returncode': 0})()
            run.side_effect = worker
            result = synthesize('测试', target, settings)
            self.assertEqual(result['provider'], 'cosy')
            settings['cosy_text_frontend'] = False
            synthesize('测试', target, settings)
            cloud.assert_not_called()

    def test_cosy_reference_content_and_transcript_invalidate_cache(self):
        root = Path(self.directory.name)
        reference = root / 'reference.wav'
        reference.write_bytes(sample_wav())
        save_settings({'provider': 'cosy', 'cosy_reference_audio': str(reference),
                       'cosy_reference_text': '参考文字'}, self.path)
        scene = Scene(id='cosy', title='demo', visual='demo', narration='今天休息一下。')
        config = {'rvc': {}, 'tts': {'settings_path': str(self.path)}}
        def generate(text, target, settings):
            target.write_bytes(sample_wav())
        def normalize(ffmpeg, source, target):
            target.write_bytes(source.read_bytes())
        with patch('src.tts.synthesize', side_effect=generate) as tts, \
                patch('src.voice.normalize_audio', side_effect=normalize), \
                patch('src.voice.duration', return_value=0.1):
            produce_voice(scene, root, config)
            produce_voice(scene, root, config)
            self.assertEqual(tts.call_count, 1)
            reference.write_bytes(sample_wav() + b'changed')
            produce_voice(scene, root, config)
            self.assertEqual(tts.call_count, 2)
            save_settings({'cosy_reference_text': '修正后的参考文字'}, self.path)
            produce_voice(scene, root, config)
            self.assertEqual(tts.call_count, 3)
            save_settings({'cosy_text_frontend': False}, self.path)
            produce_voice(scene, root, config)
            self.assertEqual(tts.call_count, 4)

    def test_text_frontend_boolean_round_trip(self):
        self.assertIs(save_settings({'cosy_text_frontend': False}, self.path)['cosy_text_frontend'], False)
        self.assertIs(load_settings(self.path)['cosy_text_frontend'], False)
        with self.assertRaises(ValueError):
            save_settings({'cosy_text_frontend': 'false'}, self.path)

    def test_fish_reference_isolated_and_invalid_requests_do_not_start_worker(self):
        root = Path(self.directory.name)
        runtime = root / '.venv/Scripts/python.exe'
        runtime.parent.mkdir(parents=True)
        runtime.touch()
        reference = root / 'fish.wav'
        reference.write_bytes(sample_wav())
        target = root / 'generated.wav'
        settings = {**DEFAULTS, 'fish_root': str(root), 'fish_reference_audio': str(reference),
                    'cosy_reference_audio': 'unused.wav', 'cosy_reference_text': '不能误用这段转写'}
        with patch('src.tts.subprocess.run') as run, patch('src.tts.minimax_request') as cloud:
            with self.assertRaisesRegex(SpeechError, '对应的文字'):
                synthesize('你好', target, settings, 'fish')
            settings['fish_reference_text'] = 'Fish 参考转写。'
            with self.assertRaisesRegex(ValueError, '原速'):
                synthesize('你好', target, {**settings, 'speed': 1.15}, 'fish')
            with self.assertRaisesRegex(ValueError, '300'):
                synthesize('字' * 301, target, settings, 'fish')
            run.assert_not_called()
            def worker(command, **kwargs):
                self.assertEqual(Path(command[1]).name, 'fish_tts_worker.py')
                request = json.loads(Path(command[-1]).read_text(encoding='utf-8'))
                self.assertEqual(request['reference'], str(reference.resolve()))
                self.assertEqual(request['reference_text'], 'Fish 参考转写。')
                self.assertEqual(request['text'], '[excited]你好！')
                self.assertEqual(kwargs['env']['HF_HUB_OFFLINE'], '1')
                target.write_bytes(sample_wav())
                return type('Result', (), {'returncode': 0})()
            run.side_effect = worker
            self.assertEqual(synthesize('[excited]你好！', target, settings, 'fish')['model'], 'Fish Audio S2 Pro')
            cloud.assert_not_called()

    def test_fish_cache_includes_reference_and_tags_are_not_subtitles(self):
        root = Path(self.directory.name)
        reference = root / 'reference.wav'
        reference.write_bytes(sample_wav())
        save_settings({'provider': 'fish', 'fish_reference_audio': str(reference),
                       'fish_reference_text': '参考文字'}, self.path)
        scene = Scene(id='fish', title='demo', visual='demo',
                      narration='<|speaker:0|>[excited]今天休息一下。[whisper]慢慢来。')
        config = {'rvc': {}, 'tts': {'settings_path': str(self.path)}}
        def generate(text, target, settings):
            target.write_bytes(sample_wav())
        def normalize(ffmpeg, source, target):
            target.write_bytes(source.read_bytes())
        with patch('src.tts.synthesize', side_effect=generate) as tts, \
                patch('src.voice.normalize_audio', side_effect=normalize), \
                patch('src.voice.duration', return_value=0.1), \
                patch('src.voice.RvcClient.convert') as convert:
            produce_voice(scene, root, config)
            produce_voice(scene, root, config)
            self.assertEqual(tts.call_count, 1)
            reference.write_bytes(sample_wav() + b'changed')
            produce_voice(scene, root, config)
            self.assertEqual(tts.call_count, 2)
            save_settings({'fish_reference_text': '修正的参考文字'}, self.path)
            produce_voice(scene, root, config)
            self.assertEqual(tts.call_count, 3)
            convert.assert_not_called()
        metadata = json.loads((root / 'voice/fish.json').read_text(encoding='utf-8'))
        self.assertNotIn('[excited]', json.dumps(metadata['captions'], ensure_ascii=False))
        self.assertNotIn('<|speaker:', json.dumps(metadata['captions'], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
