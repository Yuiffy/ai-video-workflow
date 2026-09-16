from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path


def require_ffmpeg(binary: str) -> str:
    resolved = shutil.which(binary) or (binary if Path(binary).is_file() else None)
    if not resolved:
        raise RuntimeError(f"找不到媒体工具: {binary}")
    return resolved


def run(args: list[str], **kwargs):
    result = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace", **kwargs)
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    return result


def probe(path: Path, binary: str = "ffprobe") -> dict:
    result = run([binary, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    value = json.loads(result.stdout)
    duration = float(value.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"Invalid media duration: {path}")
    return value


def duration(path: Path, binary: str = "ffprobe") -> float:
    return float(probe(path, binary)["format"]["duration"])


def concat_manifest(inputs: list[Path], path: Path):
    if not inputs or any(not item.is_file() for item in inputs):
        raise ValueError("Concat inputs must all exist")
    lines = ["file '" + item.resolve().as_posix().replace("'", "'\\''") + "'" for item in inputs]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_audio(binary: str, source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    run([binary, "-y", "-v", "error", "-i", str(source), "-vn", "-ar", "48000", "-ac", "1",
         "-c:a", "pcm_s16le", str(target)])
    return target


def concat_audio(ffmpeg_bin: str, inputs: list[Path], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = output.parent / "audio-concat.txt"
    concat_manifest(inputs, manifest)
    run([ffmpeg_bin, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(manifest),
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    return output


def concat_with_audio(ffmpeg_bin: str, video: Path, audio: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    run([ffmpeg_bin, "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-movflags", "+faststart", "-shortest", str(output)])
    return output
