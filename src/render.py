from __future__ import annotations

import math
import textwrap
from pathlib import Path

from .media import concat_manifest, duration, probe, run
from .ppt_recorder import deck_digest, open_deck, record_scene
from .storage import digest, file_digest, read_json, write_json


def stamp(seconds: float, ass=False) -> str:
    factor = 100 if ass else 1000
    units = round(seconds * factor)
    whole, fraction = divmod(units, factor)
    minute, second = divmod(whole, 60)
    hour, minute = divmod(minute, 60)
    return f"{hour}:{minute:02}:{second:02}.{fraction:02}" if ass else f"{hour:02}:{minute:02}:{second:02},{fraction:03}"


def subtitles(cues: list[dict], directory: Path, width: int, height: int, margin_ratio: float = .055):
    srt = []
    ass = [f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0",
           "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           f"Style: Default,Microsoft YaHei,{round(height*.038)},&H00FFFFFF,&H00FFFFFF,&H00101822,&H80101822,0,0,0,0,100,100,0,0,1,2,1,2,90,90,{round(height*margin_ratio)},1",
           "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for i, cue in enumerate(cues, 1):
        text = "\n".join(textwrap.wrap(cue["text"], 30, break_long_words=True, break_on_hyphens=False))
        srt.append(f"{i}\n{stamp(cue['start'])} --> {stamp(cue['end'])}\n{text}\n")
        escaped = text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", r"\N")
        ass.append(f"Dialogue: 0,{stamp(cue['start'],True)},{stamp(cue['end'],True)},Default,,0,0,0,,{escaped}")
    (directory / "captions.srt").write_text("\n".join(srt), encoding="utf-8")
    (directory / "captions.ass").write_text("\n".join(ass), encoding="utf-8-sig")


def render_project(pipeline, html_only=False) -> Path:
    from playwright.sync_api import sync_playwright
    config, project, out = pipeline.config, pipeline.project, pipeline.out
    ffmpeg, ffprobe = config.get("ffmpeg_bin", "ffmpeg"), config.get("ffprobe_bin", "ffprobe")
    fps = config.get("recording", {}).get("fps", 24)
    size = config.get("recording", {}).get("viewport", {"width": 1920, "height": 1080})
    width, height = size["width"], size["height"]
    root = out / ("web-edit" if html_only else "edit")
    root.mkdir(parents=True, exist_ok=True)
    scene_files, cues, timeline = [], [], []
    position = 0.0
    deck_hash = deck_digest(Path(project.ppt))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = open_deck(browser, Path(project.ppt), config)
            count = page.locator("[data-slide]").count()
            for i, scene in enumerate(project.scenes):
                slide = (scene.ppt_slide or i+1) - 1
                if not 0 <= slide < count:
                    raise ValueError(f"Missing HTML slide for {scene.id}")
                audio = out / "voice" / f"{scene.id}.wav"
                seconds = duration(audio, ffprobe)
                total_frames = math.ceil(seconds * fps)
                scene_seconds = total_frames / fps
                shot = None if html_only or not scene.generate_video else pipeline.video(scene.id)
                shot_frames = min(round(config.get("render", {}).get("shot_seconds", 6) * fps),
                                  total_frames // 2, math.floor(duration(shot, ffprobe) * fps)) if shot else 0
                html_seconds = (total_frames - shot_frames) / fps
                work = root / scene.id
                work.mkdir(parents=True, exist_ok=True)
                target = work / "scene.mp4"
                fingerprint = digest({"audio": file_digest(audio), "shot": file_digest(shot) if shot else None,
                                      "deck": deck_hash, "config": config.get("render"),
                                      "recording": config.get("recording"), "slide": slide, "version": 1})
                meta = work / "render.json"
                cached = meta.exists() and target.exists() and read_json(meta).get("fingerprint") == fingerprint
                if not cached:
                    print(f"render {scene.id}: {scene_seconds:.2f}s, HTML {html_seconds:.2f}s", flush=True)
                    html_clip = record_scene(page, slide, html_seconds, work / "html.mp4", config)
                    segments = []
                    if shot_frames:
                        shot_clip = work / "shot.mp4"
                        run([ffmpeg, "-y", "-v", "error", "-i", str(shot), "-an", "-vf",
                             f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}",
                             "-frames:v", str(shot_frames), "-c:v", "libx264", "-preset", "fast",
                             "-crf", "19", "-pix_fmt", "yuv420p", str(shot_clip)])
                        segments.append(shot_clip)
                    segments.append(html_clip)
                    concat_manifest(segments, work / "segments.txt")
                    run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(work/"segments.txt"),
                         "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                         "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p",
                         "-af", "apad", "-t", str(scene_seconds), "-c:a", "aac", "-ar", "48000",
                         "-b:a", "192k", "-movflags", "+faststart", str(target)])
                    write_json(meta, {"fingerprint": fingerprint, "duration": scene_seconds})
                scene_files.append(target)
                voice_meta = out / "voice" / f"{scene.id}.json"
                if not voice_meta.exists():
                    raise ValueError("Run voice to create timed captions before rendering")
                for cue in read_json(voice_meta)["captions"]:
                    cues.append({"text": cue["text"], "start": position + cue["start"],
                                 "end": position + cue["end"]})
                timeline.append({"scene": scene.id, "start": position, "end": position + scene_seconds,
                                 "shot": str(shot) if shot else None, "html_seconds": html_seconds})
                position += scene_seconds
        finally:
            browser.close()
    subtitles(cues, root, width, height, config.get("render", {}).get("subtitle_margin_ratio", .055))
    concat_manifest(scene_files, root / "scenes.txt")
    chapters = [";FFMETADATA1", "title=" + project.title]
    for scene, section in zip(project.scenes, timeline):
        chapters += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={round(section['start']*1000)}",
                     f"END={round(section['end']*1000)}", "title=" + scene.title.replace("=", " ")]
    (root/"chapters.txt").write_text("\n".join(chapters), encoding="utf-8")
    final = out / f"{project.id}{'-web' if html_only else ''}.mp4"
    partial = root / "final.partial.mp4"
    run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "scenes.txt",
         "-f", "ffmetadata", "-i", "chapters.txt", "-map", "0:v:0", "-map", "0:a:0", "-map_metadata", "1",
         "-vf", "ass=captions.ass", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000",
         "-c:v", "libx264", "-preset", config.get("render", {}).get("preset", "fast"),
         "-crf", str(config.get("render", {}).get("crf", 19)), "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-b:a", "192k", "-movflags", "+faststart", str(partial)], cwd=root)
    info = probe(partial, ffprobe)
    kinds = {s["codec_type"] for s in info["streams"]}
    if not {"video", "audio"} <= kinds or abs(float(info["format"]["duration"]) - position) > .2:
        raise RuntimeError("Rendered media failed duration/audio verification")
    partial.replace(final)
    (out / f"{project.id}.srt").write_text((root/"captions.srt").read_text(encoding="utf-8"), encoding="utf-8")
    write_json(root / "timeline.json", {"duration": position, "scenes": timeline, "probe": info})
    pipeline.stage("ppt", "done", segments=[str(root/s.id/"html.mp4") for s in project.scenes],
                   frame_rate=fps)
    pipeline.stage("render", "done", output=str(final), duration=position, timeline=str(root/"timeline.json"))
    return final
