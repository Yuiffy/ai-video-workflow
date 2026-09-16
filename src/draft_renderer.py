from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from .media import require_ffmpeg
from .models import Project


def render_draft(project: Project, output: Path, ffmpeg_bin: str = "ffmpeg") -> Path:
    ffmpeg = require_ffmpeg(ffmpeg_bin)
    work = output.parent / "draft_scenes"
    work.mkdir(parents=True, exist_ok=True)
    concat = work / "concat.txt"
    lines: list[str] = []
    for index, scene in enumerate(project.scenes, 1):
        text_file = work / f"{index:02d}.txt"
        wrapped = "\n".join(textwrap.wrap(scene.narration, width=30, break_long_words=True, break_on_hyphens=False))
        text_file.write_text(f"{scene.title}\n\n{wrapped}", encoding="utf-8")
        clip = work / f"{index:02d}.mp4"
        # A deterministic silent draft: generated shots and RVC audio can replace each scene later.
        font = "C\\:/Windows/Fonts/msyh.ttc"
        escaped_text_file = text_file.as_posix().replace(":", "\\:")
        vf = f"drawtext=fontfile='{font}':textfile='{escaped_text_file}':fontcolor=white:fontsize=42:line_spacing=18:x=120:y=360:box=1:boxcolor=0x102329cc:boxborderw=28"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c=0x0e6970:s=1920x1080:d={scene.duration}:r=30", "-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True)
        lines.append(f"file '{clip.as_posix()}'")
    concat.write_text("\n".join(lines), encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(output)], check=True, capture_output=True)
    return output
