"""Audio-bound, frame-quantized action/settle/read clocks for authored HTML scenes.

This describes timing, not visual implementation or permission to alter narration.
No provider, subprocess or filesystem access is needed to compile/evaluate a plan.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from .storage import digest


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


@dataclass(frozen=True)
class MotionBeat:
    id: str
    action: str
    start_frame: int
    settle_frame: int
    end_frame: int
    minimum_hold_frames: int


@dataclass(frozen=True)
class MotionPlan:
    scene_id: str
    fps: int
    html_start_frame: int
    beats: tuple[MotionBeat, ...]
    fingerprint: str

    def state_at(self, local_seconds: float) -> dict:
        seconds = _number(local_seconds, "clock")
        if seconds < 0:
            raise ValueError("Motion clock must be nonnegative")
        frame = self.html_start_frame + math.floor(seconds * self.fps + 1e-7)
        states = []
        for beat in self.beats:
            phase = ("before" if frame < beat.start_frame else "action" if frame < beat.settle_frame
                     else "hold" if frame < beat.end_frame else "complete")
            progress = max(0., min(1., (frame - beat.start_frame) / (beat.settle_frame - beat.start_frame)))
            states.append({"id": beat.id, "action": beat.action, "phase": phase,
                           "progress": progress, "visible": frame >= beat.start_frame})
        return {"version": 1, "scene": self.scene_id, "frame": frame, "fps": self.fps,
                "active": next((b["id"] for b in states if b["phase"] in {"action", "hold"}), None), "beats": states}

    def evidence(self) -> dict:
        return {"version": 1, "fingerprint": self.fingerprint, "fps": self.fps,
                "htmlStartFrame": self.html_start_frame,
                "beats": [{"id": b.id, "action": b.action, "startFrame": b.start_frame,
                           "settleFrame": b.settle_frame, "endFrame": b.end_frame,
                           "holdFrames": b.end_frame - b.settle_frame,
                           "minimumHoldFrames": b.minimum_hold_frames} for b in self.beats]}


def compile_motion_plan(value: dict, *, scene_id: str, audio_sha256: str,
                        audio_duration: float, fps: int, html_start: float = 0.) -> MotionPlan:
    if (not isinstance(value, dict) or type(value.get("version")) is not int
            or value.get("version") != 1 or value.get("sceneId") != scene_id):
        raise ValueError("Motion plan version/scene mismatch")
    if (not isinstance(audio_sha256, str) or len(audio_sha256) != 64
            or any(c not in '0123456789abcdef' for c in audio_sha256)
            or value.get("audioSha256") != audio_sha256):
        raise ValueError("Motion plan audio changed; retime against the current narration")
    if (isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0
            or type(value.get("fps")) is not int or value.get("fps") != fps):
        raise ValueError("Motion plan frame rate mismatch")
    duration = _number(audio_duration, "audio duration")
    offset = _number(html_start, "HTML start")
    if duration <= 0 or offset < 0 or offset >= duration:
        raise ValueError("Invalid narration/HTML window")
    if abs(_number(value.get("audioDuration"), "plan audio duration") - duration) > 1 / fps:
        raise ValueError("Motion plan narration duration mismatch")
    raw_beats = value.get("beats")
    if not isinstance(raw_beats, list) or not raw_beats or len(raw_beats) > 32:
        raise ValueError("Motion plan needs 1–32 beats")
    beats, ids = [], set()
    for raw in raw_beats:
        if (not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"].strip()
                or raw["id"] in ids or not isinstance(raw.get("action"), str) or not raw["action"].strip()):
            raise ValueError("Each motion beat needs a unique ID and semantic action")
        start, settle, end = (_number(raw.get(k), k) for k in ("start", "settle", "end"))
        minimum = _number(raw.get("minimumHold", .5), "minimumHold")
        if start < offset or settle <= start or end <= settle or end > duration + 1e-7 or minimum < .5:
            raise ValueError("Motion beat must fit the HTML window and reserve at least 0.5 seconds to read")
        frames = [math.floor(t * fps + .5) for t in (start, settle, end)]
        minimum_frames = math.ceil(minimum * fps - 1e-7)
        if frames[1] <= frames[0] or frames[2] - frames[1] < minimum_frames:
            raise ValueError("Motion beat loses its action or reading hold after frame quantization")
        if beats and frames[0] < beats[-1].end_frame:
            raise ValueError("Primary motion beats overlap or reorder")
        beats.append(MotionBeat(raw["id"], raw["action"], *frames, minimum_frames))
        ids.add(raw["id"])
    return MotionPlan(scene_id, fps, math.floor(offset * fps + .5), tuple(beats),
                      digest({"plan": value, "audio": audio_sha256, "duration": duration,
                              "fps": fps, "htmlStart": offset, "contract": 1}))
