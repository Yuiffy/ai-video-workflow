"""Produce real frame evidence for the generated clips before assembly."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PLAN = json.loads(Path(__file__).with_name("production-plan.json").read_text(encoding="utf-8"))
OUT = ROOT / PLAN["output"]
QA = OUT / "qa"
QA.mkdir(parents=True, exist_ok=True)


def run(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)], check=True)


parser = argparse.ArgumentParser()
parser.add_argument("keys", nargs="*")
args = parser.parse_args()
scenes = [scene for scene in PLAN["scenes"] + PLAN.get("repairs", []) if scene.get("type", "video") == "video"]
if args.keys:
    scenes = [scene for scene in scenes if scene["id"] in args.keys]
    assert {scene["id"] for scene in scenes} == set(args.keys)
report_file = QA / "raw-media.json"
report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.exists() else {}
for scene in scenes:
    key = scene["id"]
    source = OUT / (key + "-raw.mp4")
    if not source.exists():
        continue
    p = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)],
                       capture_output=True, encoding="utf-8", check=True)
    info = json.loads(p.stdout)
    report[key] = info
    run("-i", source, "-vf", "fps=4,scale=400:-1,tile=8x4:padding=4:margin=4", "-frames:v", "1", QA / (key + "-sheet.jpg"))
    run("-i", source, "-frames:v", "1", QA / (key + "-first.png"))
    stream = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    last_frame = int(stream["nb_frames"]) - 1
    run("-i", source, "-vf", f"select=eq(n\\,{last_frame})", "-frames:v", "1", QA / (key + "-last.png"))
    run("-i", source, "-f", "null", "-")
    print(key + " frame evidence ready", flush=True)
report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
