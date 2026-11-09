import importlib.util
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DanmakuTtsLauncherTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows process creation flags")
    def test_worker_hides_console_and_closes_inherited_handles(self):
        supervisor = load_module(
            "danmaku_tts_supervisor_test",
            "tools/danmaku_tts_supervisor.py",
        )
        options = supervisor.hidden_process_options()
        self.assertTrue(options["creationflags"] & supervisor.subprocess.CREATE_NO_WINDOW)
        self.assertTrue(options["startupinfo"].dwFlags & supervisor.subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(options["startupinfo"].wShowWindow, supervisor.subprocess.SW_HIDE)
        self.assertTrue(options["close_fds"])

    @unittest.skipUnless(os.name == "nt", "Windows process snapshot")
    def test_host_process_probe_uses_current_process_without_subprocess(self):
        supervisor = load_module(
            "danmaku_tts_supervisor_probe_test",
            "tools/danmaku_tts_supervisor.py",
        )
        current_process = Path(__import__("sys").executable).name
        self.assertTrue(supervisor.host_process_running(current_process))
        self.assertFalse(supervisor.host_process_running("definitely-not-running.exe"))

    def test_pm2_config_uses_windowless_runtime(self):
        source = (ROOT / "ecosystem.danmaku-tts.config.cjs").read_text(encoding="utf-8")
        self.assertIn("windowsHide: true", source)
        self.assertIn('DANMAKU_TTS_SILENT: "1"', source)
        self.assertIn('DANMAKU_TTS_AUTO_WARM', source)

    def test_vbs_entrypoint_uses_pythonw_and_hidden_run(self):
        source = (ROOT / "tools/start_danmaku_tts_silent.vbs").read_text(encoding="utf-8")
        self.assertIn('"pythonw.exe"', source)
        self.assertIn("shell.Run command, 0, False", source)
        self.assertNotIn("powershell.exe", source.lower())

    def test_rvc_worker_never_uses_ffmpeg_based_audio_loader(self):
        source = (ROOT / "tools/rvc_danmaku_server.py").read_text(encoding="utf-8")
        self.assertNotIn("from infer.lib.audio import load_audio", source)
        self.assertNotIn('"load_audio": load_audio', source)
        self.assertIn('"load_audio": self._load_audio', source)
        self.assertIn("import soundfile as sf", source)
        self.assertIn("from scipy.signal import resample_poly", source)
        self.assertIn("never starts an FFmpeg child process", source)


if __name__ == "__main__":
    unittest.main()
