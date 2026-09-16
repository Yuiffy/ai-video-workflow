from __future__ import annotations

from pathlib import Path

from .jimeng_cli import JimengCli
from .models import Manifest, Project, StageRecord
from .storage import read_json, write_json
from .voice import produce_voice


class Pipeline:
    def __init__(self, project_file: Path, config: dict):
        self.project_file = project_file.resolve()
        self.project = Project.from_file(self.project_file)
        self.config = config
        self.root = self.project_file.parent
        self.out = (self.root / config.get("output_dir", self.project.output)).resolve()
        path = self.out / "manifest.json"
        self.manifest = Manifest.model_validate(read_json(path)) if path.exists() else Manifest(
            project_id=self.project.id, title=self.project.title)
        if self.manifest.project_id != self.project.id:
            raise ValueError("Output directory belongs to another project")

    def stage(self, stage: str, status: str, **detail) -> Path:
        self.manifest.stages = [item for item in self.manifest.stages if item.stage != stage]
        self.manifest.stages.append(StageRecord(stage=stage, status=status, detail=detail))
        return self.write_manifest()

    def write_manifest(self) -> Path:
        path = self.out / "manifest.json"
        write_json(path, self.manifest.model_dump(mode="json"))
        return path

    def scenes(self, scene_id: str | None = None):
        result = [scene for scene in self.project.scenes if scene_id is None or scene.id == scene_id]
        if not result:
            raise ValueError(f"未知 scene: {scene_id}")
        return result

    def plan(self, dry_run: bool = True) -> Path:
        client = JimengCli(self.config["jimeng"])
        tasks = [client.plan(s.image_prompt or s.visual, self.out / "jimeng" / s.id, s.id,
                             s.duration, s.voice.reference_audio)
                 for s in self.project.scenes if s.generate_video]
        write_json(self.out / "plan.json", {"project": self.project.model_dump(mode="json"),
                                          "dry_run": True, "jimeng_tasks": tasks})
        return self.stage("plan", "done", task_count=len(tasks))

    def video(self, scene_id: str) -> Path:
        record = self.out / "jimeng" / scene_id / "job.json"
        if not record.exists():
            raise RuntimeError(f"No Dreamina job for {scene_id}")
        data = read_json(record)
        scene = self.scenes(scene_id)[0]
        if data.get("prompt") is not None and data["prompt"] != (scene.image_prompt or scene.visual):
            raise ValueError(f"Dreamina {scene_id} belongs to another prompt; review or adopt a matching job")
        if data.get("gen_status") != "success":
            raise RuntimeError(f"Dreamina {scene_id}: {data.get('gen_status')}; run poll")
        paths = data.get("videos") or [v.get("path", "") for v in data.get("result_json", {}).get("videos", [])]
        for value in paths:
            path = Path(value)
            if path.is_file() and path.stat().st_size:
                return path.resolve()
        raise RuntimeError(f"Dreamina {scene_id} has no downloaded file; run poll")

    def generate_voice(self, dry_run: bool = False, scene_id: str | None = None) -> list[Path]:
        results = []
        for scene in self.scenes(scene_id):
            path = self.out / "voice" / f"{scene.id}.wav"
            if not dry_run:
                generated = self.video(scene.id) if scene.voice.use_generated_audio else None
                path = produce_voice(scene, self.out, self.config, generated)
                self.stage("voice", "running", last_scene=scene.id)
                print(f"voice ready: {scene.id}", flush=True)
            results.append(path)
        if not dry_run:
            complete = all((self.out / "voice" / f"{s.id}.json").exists() for s in self.project.scenes)
            self.stage("voice", "done" if complete else "running", files=[str(p) for p in results])
        return results

    def generate_jimeng(self, dry_run: bool = True, scene_id: str | None = None,
                       poll_only: bool = False) -> list[dict]:
        client = JimengCli(self.config["jimeng"])
        results = []
        for scene in self.scenes(scene_id):
            if not scene.generate_video:
                continue
            target = self.out / "jimeng" / scene.id
            if dry_run:
                task = client.plan(scene.image_prompt or scene.visual, target, scene.id,
                                   scene.duration, scene.voice.reference_audio)
            elif poll_only or (target / "job.json").exists():
                # Existing paid work always resumes by ID, even if local text has changed.
                # Rendering/QA checks the selected source; changing a prompt is not consent
                # to buy another attempt.
                task = client.query(target)
            else:
                task = client.run(scene.image_prompt or scene.visual, target, scene.id,
                                  scene.duration, scene.voice.reference_audio)
            results.append(task)
            print(f"Dreamina {scene.id}: {task.get('gen_status', 'planned')}", flush=True)
        if not dry_run:
            complete = all(r.get("downloaded") for r in results)
            self.stage("jimeng", "done" if complete and scene_id is None else "running",
                       tasks=[{"scene_id": t["scene_id"], "submit_id": t.get("submit_id"),
                               "status": t.get("gen_status")} for t in results])
        return results
