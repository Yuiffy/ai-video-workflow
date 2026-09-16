from __future__ import annotations

import json
from pathlib import Path

from .jimeng_cli import JimengCli
from .models import Manifest, Project, StageRecord
from .rvc_client import RvcClient


class Pipeline:
    def __init__(self, project_file: Path, config: dict):
        self.project_file = project_file
        self.project = Project.from_file(project_file)
        self.config = config
        self.root = project_file.parent
        self.out = (self.root / config.get("output_dir", self.project.output)).resolve()
        self.manifest = Manifest(project_id=self.project.id, title=self.project.title)

    def write_manifest(self) -> Path:
        self.out.mkdir(parents=True, exist_ok=True)
        path = self.out / "manifest.json"
        path.write_text(self.manifest.model_dump_json(indent=2), encoding="utf-8")
        return path

    def plan(self, dry_run: bool = True) -> Path:
        jimeng_cfg = self.config["jimeng"]
        jimeng = JimengCli(jimeng_cfg["command"], jimeng_cfg["model"], jimeng_cfg["ratio"], jimeng_cfg["duration"], jimeng_cfg.get("video_resolution", "720p"), jimeng_cfg.get("executable"), jimeng_cfg.get("images", []), int(jimeng_cfg.get("poll", 0)))
        tasks = [jimeng.plan(scene.image_prompt or scene.visual, self.out / "jimeng" / scene.id, scene.id) for scene in self.project.scenes if scene.image_prompt or scene.visual]
        plan = {"project": self.project.model_dump(mode="json"), "dry_run": dry_run, "jimeng_tasks": tasks}
        (self.out / "plan.json").parent.mkdir(parents=True, exist_ok=True)
        (self.out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        self.manifest.stages.extend([StageRecord(stage="plan", status="done", detail={"task_count": len(tasks)}), StageRecord(stage="voice", status="planned"), StageRecord(stage="ppt", status="planned"), StageRecord(stage="jimeng", status="planned"), StageRecord(stage="render", status="planned")])
        return self.write_manifest()

    def generate_voice(self, dry_run: bool = False, scene_id: str | None = None) -> list[Path]:
        cfg = self.config.get("rvc", {})
        bridge = str((Path(__file__).parents[1] / "tools" / "rvc_convert.py").resolve())
        values = {"runtime_python": cfg.get("runtime_python", "python"), "rvc_root": cfg.get("rvc_root", ""), "rvc_bridge": bridge, "sapi_tts": str((Path(__file__).parents[1] / "tools" / "sapi_tts.py").resolve()), "model": cfg.get("model", "suiV2.pth"), "index": cfg.get("index", ""), "pitch": str(cfg.get("pitch", 0))}
        commands = {"tts": cfg.get("tts_command"), "convert": cfg.get("convert_command"), "values": values}
        client = RvcClient(cfg.get("base_url", "http://127.0.0.1:7865"), cfg.get("tts_path", "/api/tts"), cfg.get("convert_path", "/api/convert"), float(cfg.get("timeout_seconds", 180)), cfg.get("mode", "http"), commands)
        scenes = [s for s in self.project.scenes if scene_id is None or s.id == scene_id]
        if scene_id and not scenes:
            raise ValueError(f"未知 scene: {scene_id}")
        results: list[Path] = []
        for scene in scenes:
            raw = self.out / "voice" / f"{scene.id}.mp3"
            converted = self.out / "voice" / f"{scene.id}.wav"
            if dry_run:
                results.append(converted if not scene.voice.already_target_voice else raw)
                continue
            client.tts(scene.narration, raw, scene.voice.speaker, scene.voice.speed)
            if scene.voice.already_target_voice:
                results.append(raw)
            else:
                results.append(client.convert(raw, converted, scene.voice.speaker, scene.voice.pitch))
        return results
