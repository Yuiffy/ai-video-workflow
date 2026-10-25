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
from src.storage import write_json, read_json, file_digest
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

    def test_motion_plan_intro_clock_cache_and_audio_binding(self):
        (self.root/"deck.html").write_text(
            '<html><body><div data-slide>Motion</div><script>'
            'window.motionPlanVersion=1; window.renderAt=v=>{'
            'if(!v.motion || v.motion.frame<3)throw Error("Missing absolute clock");'
            'document.body.style.background=v.motion.active?"#357":"#fff";'
            'document.body.dataset.frame=v.motion.frame;};</script></body></html>', encoding="utf-8")
        write_json(self.root/"project.json", {"id": "motion", "title": "Motion",
            "script": "script.md", "ppt": "deck.html", "scenes": [{"id": "a", "title": "A",
                "narration": "hello", "visual": "a", "motion_plan": "motion.json"}]})
        pipeline = Pipeline(self.root/"project.json", {"rvc": {}, "recording": {
            "viewport": {"width": 320, "height": 180}, "fps": 12},
            "render": {"preset": "ultrafast", "shot_seconds": .25}})
        voice_dir = pipeline.out/"voice"
        voice_dir.mkdir(parents=True)
        shutil.copy2(self.audio, voice_dir/"a.wav")
        write_json(voice_dir/"a.json", {"captions": [{"text": "hello", "start": 0, "end": 1.17}]})
        plan = {"version": 1, "sceneId": "a", "audioSha256": file_digest(self.audio),
                "audioDuration": 1.17, "fps": 12, "beats": [{"id": "flow", "action": "Pass input",
                    "start": .25, "settle": .5, "end": 1.17}]}
        write_json(self.root/"motion.json", plan)
        shot = self.root/"shot.mp4"
        run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
             "color=c=black:s=320x180:r=12:d=1", "-c:v", "libx264", str(shot)])
        with patch.object(pipeline, "video", return_value=shot):
            output = render_project(pipeline)
            self.assertAlmostEqual(duration(output), 1.25, delta=.08)
            section = read_json(pipeline.out/"edit/timeline.json")["scenes"][0]
            self.assertEqual(section["motionPlan"]["htmlStartFrame"], 3)
            self.assertGreaterEqual(section["motionPlan"]["beats"][0]["holdFrames"], 6)
            meta = pipeline.out/"edit/a/render.json"
            first = read_json(meta)["fingerprint"]
            with patch("src.render.record_scene", side_effect=AssertionError("Cache miss")):
                render_project(pipeline)
            plan["beats"][0]["settle"] = .5833333333333334
            write_json(self.root/"motion.json", plan)
            render_project(pipeline)
            self.assertNotEqual(first, read_json(meta)["fingerprint"])
            plan["audioSha256"] = "b"*64
            write_json(self.root/"motion.json", plan)
            with self.assertRaisesRegex(ValueError, "audio changed"):
                render_project(pipeline)


if __name__ == "__main__":
    unittest.main()
