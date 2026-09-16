"""Render local HTML on an explicit frame clock for repeatable narration timing."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path
from .storage import digest, file_digest


def deck_digest(html: Path) -> str:
    """Invalidate cached recordings when a local script/style changes as well."""
    assets = sorted(p for p in html.parent.rglob("*") if p.is_file() and
                    p.suffix.lower() in {".html", ".js", ".css", ".svg", ".png", ".jpg", ".woff2"})
    return digest([(str(p.relative_to(html.parent)), file_digest(p)) for p in assets])


def record_scene(page, slide: int, seconds: float, output: Path, config: dict) -> Path:
    fps = int(config.get("recording", {}).get("fps", 24))
    size = config.get("recording", {}).get("viewport", {"width": 1920, "height": 1080})
    frames = math.ceil(seconds * fps)
    if frames <= 0:
        raise ValueError("HTML segment must contain at least one frame")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial.mp4")
    args = [config.get("ffmpeg_bin", "ffmpeg"), "-y", "-v", "error", "-f", "image2pipe",
            "-vcodec", "mjpeg", "-framerate", str(fps), "-i", "-", "-an", "-c:v", "libx264",
            "-preset", config.get("render", {}).get("preset", "fast"), "-crf", "19",
            "-pix_fmt", "yuv420p", "-r", str(fps), "-s", f"{size['width']}x{size['height']}",
            "-movflags", "+faststart", str(partial)]
    with output.with_suffix(".ffmpeg.log").open("wb") as log:
        encoder = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=log, stdout=subprocess.DEVNULL)
        try:
            for frame in range(frames):
                page.evaluate("value => window.renderAt(value)",
                              {"slide": slide, "time": frame / fps, "duration": seconds})
                encoder.stdin.write(page.screenshot(type="jpeg", quality=92))
            encoder.stdin.close()
            if encoder.wait(timeout=120):
                raise RuntimeError(f"HTML encoder failed; inspect {output.with_suffix('.ffmpeg.log')}")
        except BaseException:
            encoder.kill()
            encoder.wait()
            raise
    partial.replace(output)
    return output


def open_deck(browser, html: Path, config: dict):
    size = config.get("recording", {}).get("viewport", {"width": 1920, "height": 1080})
    page = browser.new_page(viewport=size, device_scale_factor=1)
    page.goto(html.resolve().as_uri(), wait_until="load")
    page.evaluate("document.fonts.ready")
    if not page.evaluate("typeof window.renderAt === 'function'"):
        raise ValueError("Deck must implement window.renderAt({slide, time, duration})")
    return page
