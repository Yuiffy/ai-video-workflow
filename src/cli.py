from __future__ import annotations

import argparse
import json
from pathlib import Path

from .draft_renderer import render_draft
from .pipeline import Pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="AI video workflow")
    parser.add_argument("command", choices=["plan", "draft", "run"])
    parser.add_argument("project", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config.exists() else json.loads(Path(__file__).parents[1].joinpath("config.example.json").read_text(encoding="utf-8"))
    pipeline = Pipeline(args.project, config)
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
