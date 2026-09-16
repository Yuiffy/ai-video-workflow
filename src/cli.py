from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from filelock import FileLock

from .jimeng_cli import JimengCli
from .media import concat_audio
from .pipeline import Pipeline
from .render import render_project
from .storage import read_json


def load_config(path: Path | None) -> dict:
    root = Path(__file__).resolve().parents[1]
    if path is None:
        path = root / "config.json"
        if not path.exists():
            path = root / "config.example.json"
    config = read_json(path)
    for variable, key in [("FFMPEG_BIN", "ffmpeg_bin"), ("FFPROBE_BIN", "ffprobe_bin")]:
        if os.environ.get(variable):
            config[key] = os.environ[variable]
    if os.environ.get("DREAMINA_CLI"):
        config["jimeng"]["executable"] = os.environ["DREAMINA_CLI"]
    if os.environ.get("RVC_BASE_URL"):
        config["rvc"].update(mode="http", base_url=os.environ["RVC_BASE_URL"])
    for key in ("images", "audio_references"):
        config["jimeng"][key] = [str((path.resolve().parent / item).resolve())
                                 for item in config["jimeng"].get(key, [])]
    return config


def doctor(config: dict) -> dict:
    tools = {}
    for name, command in {"ffmpeg": config.get("ffmpeg_bin", "ffmpeg"),
                          "ffprobe": config.get("ffprobe_bin", "ffprobe"),
                          "dreamina": config["jimeng"].get("executable", "dreamina")}.items():
        tools[name] = shutil.which(command) or (command if Path(command).is_file() else None)
    voice = config.get("rvc", {})
    health = None
    if voice.get("mode") == "http":
        import httpx
        try:
            health = httpx.get(voice["base_url"].rstrip("/") + "/health", timeout=4, trust_env=False).json()
        except (httpx.HTTPError, ValueError) as exc:
            health = {"error": str(exc)}
    else:
        rvc_root = Path(voice.get("rvc_root", ""))
        health = {"runtime": Path(voice.get("runtime_python", "")).is_file(),
                  "weights": (rvc_root / "assets/weights" / voice.get("model", "")).is_file(),
                  "index": not voice.get("index") or Path(voice["index"]).is_file()}
    return {"tools": tools, "voice": health}


def main() -> int:
    parser = argparse.ArgumentParser(description="AI video: Dreamina + web diagrams + local TTS/RVC")
    parser.add_argument("command", choices=["plan", "doctor", "status", "voice", "audio", "jimeng",
                                          "poll", "adopt", "record", "render", "run"])
    parser.add_argument("project", type=Path, nargs="?")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Plan only; never call providers")
    parser.add_argument("--scene")
    parser.add_argument("--submit-id", help="adopt an already submitted Dreamina job")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == "doctor":
        print(json.dumps(doctor(config), ensure_ascii=False, indent=2))
        return 0
    if not args.project:
        parser.error("project is required for this command")
    pipeline = Pipeline(args.project, config)
    pipeline.out.mkdir(parents=True, exist_ok=True)
    with FileLock(str(pipeline.out / ".pipeline.lock"), timeout=0):
        if args.dry_run or args.command == "plan":
            print(f"plan: {pipeline.plan()}")
        elif args.command == "status":
            print(pipeline.manifest.model_dump_json(indent=2))
        elif args.command == "voice":
            pipeline.generate_voice(scene_id=args.scene)
        elif args.command == "audio":
            files = [pipeline.out / "voice" / f"{s.id}.wav" for s in pipeline.project.scenes]
            print(concat_audio(config.get("ffmpeg_bin", "ffmpeg"), files,
                               pipeline.out / "voice" / f"{pipeline.project.id}-narration.wav"))
        elif args.command in {"jimeng", "poll"}:
            jobs = pipeline.generate_jimeng(False, args.scene, poll_only=args.command == "poll")
            if not all(job.get("downloaded") for job in jobs):
                print("Remote work remains pending. Resume with poll; no new submission is needed.")
                return 2
        elif args.command == "adopt":
            if not args.scene or not args.submit_id:
                parser.error("adopt requires --scene and --submit-id")
            scene = pipeline.scenes(args.scene)[0]
            job = JimengCli(config["jimeng"]).adopt(pipeline.out/"jimeng"/scene.id, args.submit_id,
                                                   scene.image_prompt or scene.visual, scene.id)
            print(f"adopted {scene.id}: {job['gen_status']}")
        elif args.command in {"record", "render"}:
            print(render_project(pipeline, html_only=args.command == "record"))
        elif args.command == "run":
            pipeline.plan()
            jobs = pipeline.generate_jimeng(False)
            if not all(job.get("downloaded") for job in jobs):
                print("Generation is pending. Resume this same run command later.")
                return 2
            pipeline.generate_voice()
            print(render_project(pipeline))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
