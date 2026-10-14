"""Cut the generated intro and repeat the verified dance loop on the source music."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PLAN = json.loads(Path(__file__).with_name("production-plan.json").read_text(encoding="utf-8"))
OUT = ROOT / PLAN["output"]


def run(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)], check=True)


def probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                            capture_output=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def main():
    edit = OUT / "edit"
    edit.mkdir(parents=True, exist_ok=True)
    width, height = PLAN["assembly"]["size"]
    fps = PLAN["assembly"]["fps"]
    selected = PLAN["assembly"].get("selected_sources", {})
    # Keep the terminal frame available when FFmpeg rounds the input EOF timestamp.
    vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,tpad=stop_mode=clone:stop_duration=0.1,fps={fps}"
    for scene in PLAN["scenes"]:
        source = OUT / (selected.get(scene["id"], scene["id"]) + "-raw.mp4")
        seconds = float(probe(source)["format"]["duration"])
        if seconds + 1 / fps < scene["edit_duration"]:
            raise ValueError(f"{scene['id']} is shorter than the planned cut")
        run("-i", source, "-an", "-vf", vf, "-frames:v", round(scene["edit_duration"] * fps),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", edit / (scene["id"] + ".mp4"))
        encoded = probe(edit / (scene["id"] + ".mp4"))
        stream = next(stream for stream in encoded["streams"] if stream["codec_type"] == "video")
        assert int(stream["nb_frames"]) == round(scene["edit_duration"] * fps)
    run("-stream_loop", "3", "-i", edit / "dance.mp4", "-an", "-frames:v", 810,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", edit / "dance-repeated.mp4")
    inputs = edit / "inputs.txt"
    inputs.write_text("file 'intro.mp4'\nfile 'dance-repeated.mp4'\n", encoding="utf-8")
    target = OUT / PLAN["assembly"].get("output_file", "sui-suddenly-life.mp4")
    run("-f", "concat", "-safe", "0", "-i", inputs, "-i", ROOT / PLAN["assembly"]["audio_source"],
        "-map", "0:v:0", "-map", "1:a:0", "-t", "32.6", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000", "-movflags", "+faststart", "-metadata", "title=" + PLAN["title"], target)
    final = probe(target)
    assert abs(float(final["format"]["duration"]) - 32.6) < 0.05
    assert {"video", "audio"}.issubset({s["codec_type"] for s in final["streams"]})
    video = next(stream for stream in final["streams"] if stream["codec_type"] == "video")
    assert int(video["nb_frames"]) == 978
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(target), "-f", "null", "-"], check=True)
    report = {"selected_sources": selected, "duration": 32.6, "video_frames": 978, "intro_frames": 168, "loop_frames": 207,
              "dance_frames": 810, "source_music": PLAN["assembly"]["audio_source"], "probe": final,
              "full_decode": "passed"}
    (OUT / "media-qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    run("-i", target, "-vf", "fps=1/2,scale=400:-1,tile=4x5:padding=4:margin=4", "-frames:v", "1", OUT / "contact-sheet.jpg")
    run("-ss", "7", "-i", target, "-frames:v", "1", OUT / "poster.jpg")
    print(target, flush=True)


if __name__ == "__main__":
    main()
