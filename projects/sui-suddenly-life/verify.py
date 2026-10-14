"""Inspect the actual cut and loop boundaries in the delivered film."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
PLAN = json.loads(Path(__file__).with_name("production-plan.json").read_text(encoding="utf-8"))
OUT = ROOT / PLAN["output"]
QA = OUT / "qa"
QA.mkdir(parents=True, exist_ok=True)


def frame(path, index, target):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
                    "-vf", f"select=eq(n\\,{index})", "-frames:v", "1", str(target)], check=True)
    return Image.open(target).convert("RGB")


def main():
    target = OUT / PLAN["assembly"].get("output_file", "sui-suddenly-life.mp4")
    boundaries = [168, 375, 582, 789]
    sheet = Image.new("RGB", (1600, 4 * 249), "#18151f")
    draw = ImageDraw.Draw(sheet)
    differences = {}
    for row, boundary in enumerate(boundaries):
        images = []
        for col, index in enumerate(range(boundary - 2, boundary + 2)):
            picture = frame(target, index, QA / f"final-frame-{index}.png")
            images.append(np.asarray(picture, dtype=np.int16))
            sheet.paste(picture.resize((400, 225)), (col * 400, row * 249 + 24))
            draw.text((col * 400 + 10, row * 249 + 6), f"Frame {index} / {index / 30:.3f}s", fill="white")
        differences[str(boundary / 30)] = float(np.abs(images[1] - images[2]).mean())
    sheet.save(QA / "final-boundaries.jpg", quality=94)
    frame(target, 0, QA / "final-first.png")
    frame(target, 977, QA / "final-last.png")
    loop_first = frame(OUT / "edit/dance.mp4", 0, QA / "selected-loop-first.png")
    loop_last = frame(OUT / "edit/dance.mp4", 206, QA / "selected-loop-last.png")
    loop_delta = float(np.abs(np.asarray(loop_first, dtype=np.int16) - np.asarray(loop_last, dtype=np.int16)).mean())
    report = json.loads((OUT / "media-qa.json").read_text(encoding="utf-8"))
    video = next(stream for stream in report["probe"]["streams"] if stream["codec_type"] == "video")
    assert int(video["nb_frames"]) == 978
    assert video["avg_frame_rate"] == "30/1"
    report["boundary_pixel_differences"] = differences
    report["selected_loop_first_last_difference"] = loop_delta
    report["boundary_evidence"] = str(QA / "final-boundaries.jpg")
    (OUT / "media-qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"frames": 978, "boundary_differences": differences, "loop_first_last_difference": loop_delta}))


if __name__ == "__main__":
    main()
