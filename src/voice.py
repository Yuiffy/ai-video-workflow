from __future__ import annotations

import re
import textwrap
from pathlib import Path

from .media import concat_audio, duration, normalize_audio, run
from .rvc_client import RvcClient
from .storage import digest, file_digest, read_json, write_json


def phrases(text: str) -> list[str]:
    chunks = re.findall(r"[^，。！？；,.!?;]+[，。！？；,.!?;]?", text)
    return [part.strip() for chunk in chunks for part in
            textwrap.wrap(chunk, 32, break_long_words=True, break_on_hyphens=False) if part.strip()]


def produce_voice(scene, output: Path, config: dict, generated_audio: Path | None = None) -> Path:
    cfg = config["rvc"]
    client = RvcClient(cfg)
    ffmpeg, ffprobe = config.get("ffmpeg_bin", "ffmpeg"), config.get("ffprobe_bin", "ffprobe")
    directory = output / "voice"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{scene.id}.wav"
    metadata = directory / f"{scene.id}.json"
    source = Path(scene.voice.source_audio) if scene.voice.source_audio else generated_audio
    fingerprint = digest({"narration": scene.narration, "voice": scene.voice.model_dump(),
                          "config": cfg, "source": file_digest(source) if source else None,
                          "voice_pipeline": 2})
    if metadata.exists() and target.is_file():
        old = read_json(metadata)
        if old.get("fingerprint") == fingerprint and old.get("sha256") == file_digest(target):
            return target
    work = directory / scene.id
    work.mkdir(parents=True, exist_ok=True)
    raw = work / "source.wav"
    captions = []
    if source:
        normalize_audio(ffmpeg, source, raw)
        captions = [{"text": scene.narration, "start": 0, "end": duration(raw, ffprobe)}]
    else:
        position = 0
        sources = []
        for i, phrase in enumerate(phrases(scene.narration)):
            path = work / f"tts-{i:03d}.wav"
            client.tts(phrase, path, scene.voice.speed)
            seconds = duration(path, ffprobe)
            captions.append({"text": phrase, "start": position, "end": position + seconds})
            position += seconds
            sources.append(path)
        concat_audio(ffmpeg, sources, raw)
    if scene.voice.already_target_voice:
        voice_source = raw
        conversion = "skipped: input explicitly marked as target voice"
    else:
        voice_source = client.convert(raw, work / "converted.wav", scene.voice.pitch)
        conversion = "rvc"
    temporary = work / "normalized.wav"
    normalize_audio(ffmpeg, voice_source, temporary)
    seconds = duration(temporary, ffprobe)
    factor = seconds / captions[-1]["end"]
    for caption in captions:
        caption["start"] *= factor
        caption["end"] *= factor
    temporary.replace(target)
    write_json(metadata, {"fingerprint": fingerprint, "sha256": file_digest(target),
                         "duration": seconds, "conversion": conversion,
                         "caption_timing": "source-chunks" if not source else "scene-only",
                         "captions": captions})
    return target
