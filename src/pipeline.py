from __future__ import annotations

import json
from pathlib import Path

from .jimeng_cli import JimengCli
from .models import Manifest, Project, StageRecord


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
        jimeng = JimengCli(jimeng_cfg["command"], jimeng_cfg["model"], jimeng_cfg["ratio"], jimeng_cfg["duration"])
        tasks = [jimeng.plan(scene.image_prompt or scene.visual, self.out / "jimeng" / scene.id, scene.id) for scene in self.project.scenes if scene.image_prompt or scene.visual]
        plan = {"project": self.project.model_dump(mode="json"), "dry_run": dry_run, "jimeng_tasks": tasks}
        (self.out / "plan.json").parent.mkdir(parents=True, exist_ok=True)
        (self.out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        self.manifest.stages.extend([StageRecord(stage="plan", status="done", detail={"task_count": len(tasks)}), StageRecord(stage="voice", status="planned"), StageRecord(stage="ppt", status="planned"), StageRecord(stage="jimeng", status="planned"), StageRecord(stage="render", status="planned")])
        return self.write_manifest()
