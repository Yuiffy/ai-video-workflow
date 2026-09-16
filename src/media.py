from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def require_ffmpeg(binary: str) -> str:
    resolved = shutil.which(binary) or (binary if Path(binary).exists() else None)
    if not resolved:
        raise RuntimeError(f"找不到 FFmpeg: {binary}")
    return resolved


def concat_with_audio(ffmpeg_bin: str, video: Path, audio: Path, output: Path) -> Path:
    require_ffmpeg(ffmpeg_bin)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg_bin, "-y", "-i", str(video), "-i", str(audio), "-c:v", "copy", "-c:a", "aac", "-shortest", str(output)], check=True, capture_output=True)
    return output
