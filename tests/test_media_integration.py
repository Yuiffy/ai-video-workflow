"""Real offline media tests; no provider calls and no external model downloads."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.media import duration, probe, run
from src.models import Scene
from src.pipeline import Pipeline
from src.render import render_project
from src.storage import write_json
from src.voice import produce_voice


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is needed")
class MediaIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audio = self.root/"source.wav"
        run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
             "sine=frequency=330:duration=1.17", "-ar", "48000", str(self.audio)])

    def test_target_voice_input_bypasses_tts_and_rvc(self):
        scene = Scene(id="a", title="a", narration="保留输入", visual="a",
                      voice={"source_audio": str(self.audio), "already_target_voice": True})
        with patch("src.voice.RvcClient") as provider:
            path = produce_voice(scene, self.root, {"rvc": {}})
            provider.return_value.tts.assert_not_called()
            provider.return_value.convert.assert_not_called()
        self.assertAlmostEqual(duration(path), 1.17, places=2)

    def test_renderer_preserves_longer_narration_and_frame_timing(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright is needed")
        # An extremely short HTML scene clock keeps this integration test inexpensive.
        (self.root/"deck.html").write_text(
            '<html><body style="background:#123;color:white"><div data-slide>Timeline</div>'
            '<script>window.renderAt=v=>{document.body.style.opacity=1}</script></body></html>',
            encoding="utf-8")
        project = {"id": "test", "title": "Test", "script": "script.md", "ppt": "deck.html",
                   "scenes": [{"id": "a", "title": "A", "narration": "hello", "visual": "a",
                               "duration": 4, "generate_video": False, "ppt_slide": 1}]}
        write_json(self.root/"project.json", project)
        pipeline = Pipeline(self.root/"project.json", {"rvc": {}, "recording": {
            "viewport": {"width": 320, "height": 180}, "fps": 12}, "render": {"preset": "ultrafast"}})
        voice_dir = pipeline.out/"voice"
        voice_dir.mkdir(parents=True)
        shutil.copy2(self.audio, voice_dir/"a.wav")
        write_json(voice_dir/"a.json", {"captions": [{"text": "hello", "start": 0, "end": 1.17}]})
        output = render_project(pipeline)
        info = probe(output)
        self.assertTrue({"audio", "video"} <= {s["codec_type"] for s in info["streams"]})
        self.assertAlmostEqual(duration(output), 1.25, delta=.08)
        self.assertIn("hello", (pipeline.out/"test.srt").read_text())
        states = {stage.stage: stage.status for stage in pipeline.manifest.stages}
        self.assertEqual(states["ppt"], "done")
        self.assertEqual(states["render"], "done")


if __name__ == "__main__":
    unittest.main()
