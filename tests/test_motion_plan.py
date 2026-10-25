"""Narration changes and seeking must never silently reuse stale motion timing."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.models import Project
from src.motion_plan import compile_motion_plan


class MotionPlanTests(unittest.TestCase):
    def setUp(self):
        self.raw = {"version": 1, "sceneId": "a", "audioSha256": "a" * 64,
                    "audioDuration": 4, "fps": 12,
                    "beats": [{"id": "flow", "action": "Pass evidence into review",
                               "start": 1, "settle": 2, "end": 4, "minimumHold": 1}]}

    def compile(self, raw=None, **kwargs):
        return compile_motion_plan(raw or self.raw, **{
            "scene_id": "a", "audio_sha256": "a" * 64, "audio_duration": 4,
            "fps": 12, **kwargs})

    def test_absolute_audio_clock_with_generated_intro_and_reverse_seek(self):
        plan = self.compile(html_start=1)
        self.assertEqual(plan.state_at(0)["frame"], 12)
        self.assertEqual(plan.state_at(.5)["beats"][0]["progress"], .5)
        first = plan.state_at(.5)
        self.assertEqual(plan.state_at(1)["beats"][0]["phase"], "hold")
        self.assertEqual(plan.state_at(3)["beats"][0]["phase"], "complete")
        self.assertEqual(plan.state_at(.5), first)
        self.assertNotEqual(plan.fingerprint, self.compile().fingerprint)

    def test_rejects_stale_audio_and_invalid_clocks(self):
        for kwargs in ({"audio_sha256": "b"*64}, {"audio_duration": 5},
                       {"fps": 24}, {"html_start": 1.1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.compile(**kwargs)
        for changes in ({"settle": 3.8}, {"start": 2}, {"end": 5},
                        {"minimumHold": .1}, {"start": float("nan")}):
            raw = copy.deepcopy(self.raw)
            raw["beats"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.compile(raw)
        for key in ("version", "fps"):
            raw = copy.deepcopy(self.raw)
            raw[key] = True
            with self.assertRaises(ValueError):
                self.compile(raw)

    def test_rejects_overlapping_or_duplicate_actions(self):
        raw = copy.deepcopy(self.raw)
        raw["beats"].append({**raw["beats"][0], "id": "next"})
        with self.assertRaises(ValueError):
            self.compile(raw)
        raw["beats"][1]["id"] = "flow"
        with self.assertRaises(ValueError):
            self.compile(raw)

    def test_subframe_action_cannot_disappear(self):
        raw = copy.deepcopy(self.raw)
        raw["beats"][0].update(start=1.001, settle=1.002)
        with self.assertRaises(ValueError):
            self.compile(raw)

    def test_optional_project_path_is_relative_to_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/"project.json"
            data = {"id": "test", "title": "test", "script": "script.md", "ppt": "deck.html",
                    "scenes": [{"id": "a", "title": "A", "narration": "A", "visual": "A",
                                "motion_plan": "timing/a.json"}]}
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(Project.from_file(path).scenes[0].motion_plan,
                             str((root/"timing/a.json").resolve()))
            del data["scenes"][0]["motion_plan"]
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertIsNone(Project.from_file(path).scenes[0].motion_plan)


if __name__ == "__main__":
    unittest.main()
