from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict, model_validator


class VoiceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speaker: str = "鹿饼"
    reference_audio: str | None = None
    already_target_voice: bool = False
    source_audio: str | None = None
    use_generated_audio: bool = False
    speed: float = Field(default=1.0, gt=0, le=2)
    pitch: int | None = Field(default=None, ge=-24, le=24)


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    title: str
    narration: str
    visual: str
    duration: int = Field(default=8, ge=2, le=60)
    ppt_slide: int | None = None
    voice: VoiceSpec = Field(default_factory=VoiceSpec)
    image_prompt: str | None = None
    generate_video: bool = True


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    language: str = "zh-CN"
    description: str = ""
    script: str
    ppt: str
    storyboard: str | None = None
    output: str = "outputs"
    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_scenes(self):
        if len({s.id for s in self.scenes}) != len(self.scenes):
            raise ValueError("Scene IDs must be unique")
        return self

    @classmethod
    def from_file(cls, path: Path) -> "Project":
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        base = path.parent
        for key in ("script", "ppt", "storyboard"):
            if data.get(key):
                data[key] = str((base / data[key]).resolve())
        for scene in data["scenes"]:
            for key in ("source_audio", "reference_audio"):
                if scene.get("voice", {}).get(key):
                    scene["voice"][key] = str((base / scene["voice"][key]).resolve())
        return cls.model_validate(data)


class StageRecord(BaseModel):
    stage: Literal["plan", "voice", "ppt", "jimeng", "render"]
    status: Literal["planned", "running", "done", "skipped", "failed"]
    detail: dict = Field(default_factory=dict)


class Manifest(BaseModel):
    project_id: str
    title: str
    stages: list[StageRecord] = Field(default_factory=list)
