from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class VoiceSpec(BaseModel):
    speaker: str = "鹿饼"
    reference_audio: str | None = None
    already_target_voice: bool = False
    speed: float = 1.0
    pitch: int = 0


class Scene(BaseModel):
    id: str
    title: str
    narration: str
    visual: str
    duration: int = Field(default=8, ge=2, le=60)
    ppt_slide: int | None = None
    voice: VoiceSpec = Field(default_factory=VoiceSpec)
    image_prompt: str | None = None


class Project(BaseModel):
    id: str
    title: str
    language: str = "zh-CN"
    description: str = ""
    script: str
    ppt: str
    output: str = "outputs"
    scenes: list[Scene]

    @classmethod
    def from_file(cls, path: Path) -> "Project":
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        base = path.parent
        for key in ("script", "ppt"):
            data[key] = str((base / data[key]).resolve())
        return cls.model_validate(data)


class StageRecord(BaseModel):
    stage: Literal["plan", "voice", "ppt", "jimeng", "render"]
    status: Literal["planned", "running", "done", "skipped", "failed"]
    detail: dict = Field(default_factory=dict)


class Manifest(BaseModel):
    project_id: str
    title: str
    stages: list[StageRecord] = Field(default_factory=list)

