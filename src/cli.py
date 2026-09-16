from __future__ import annotations

import argparse
import json
from pathlib import Path

from .draft_renderer import render_draft
from .pipeline import Pipeline
from .ppt_recorder import record_ppt_sync


def main() -> int:
    parser = argparse.ArgumentParser(description="AI video workflow")
    parser.add_argument("command", choices=["plan", "voice", "record", "draft", "run"])
    parser.add_argument("project", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scene", default=None, help="只处理一个 scene id")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config.exists() else json.loads(Path(__file__).parents[1].joinpath("config.example.json").read_text(encoding="utf-8"))
    pipeline = Pipeline(args.project, config)
    if args.command == "record":
        rec = config.get("recording", {})
        viewport = rec.get("viewport", {"width": 1920, "height": 1080})
        html = Path(pipeline.project.ppt)
        output = pipeline.out / "ppt" / f"{pipeline.project.id}.webm"
        result = record_ppt_sync(html, output, int(rec.get("seconds_per_slide", 7)), (int(viewport["width"]), int(viewport["height"])), int(rec.get("fps", 30)))
        print(f"ppt: {result}")
        return 0
    if args.command == "voice":
        for path in pipeline.generate_voice(dry_run=args.dry_run, scene_id=args.scene):
            print(f"voice: {path}")
        return 0
    if args.command == "draft":
        output = pipeline.out / f"{pipeline.project.id}-draft.mp4"
        print(f"draft: {render_draft(pipeline.project, output, config.get('ffmpeg_bin', 'ffmpeg'))}")
        return 0
    path = pipeline.plan(dry_run=args.dry_run or args.command == "plan")
    print(f"manifest: {path}")
    print(f"plan: {(path.parent / 'plan.json')}")
    if args.command == "run" and not args.dry_run:
        print("run mode currently prepares the manifest; execute voice/record/render stages with their provider adapters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
