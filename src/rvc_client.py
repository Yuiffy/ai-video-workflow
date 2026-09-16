from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


class RvcError(RuntimeError):
    pass


class RvcClient:
    def __init__(self, base_url: str, tts_path: str = "/api/tts", convert_path: str = "/api/convert", timeout: float = 180):
        self.base_url = base_url.rstrip("/")
        self.tts_path = tts_path
        self.convert_path = convert_path
        self.timeout = timeout

    def _save_response(self, response: httpx.Response, target: Path) -> Path:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "audio" in content_type or response.content[:4] in (b"RIFF", b"ID3", b"\xff\xfb"):
            target.write_bytes(response.content)
            return target
        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise RvcError("RVC 返回既不是音频也不是 JSON") from exc
        audio_path = payload.get("audio_path") or payload.get("path") or payload.get("url")
        if not audio_path:
            raise RvcError(f"RVC 响应缺少 audio_path: {payload}")
        if str(audio_path).startswith("http"):
            downloaded = httpx.get(audio_path, timeout=self.timeout)
            downloaded.raise_for_status()
            target.write_bytes(downloaded.content)
        else:
            target.write_bytes(Path(audio_path).read_bytes())
        return target

    def tts(self, text: str, target: Path, speaker: str, speed: float = 1.0) -> Path:
        response = httpx.post(self.base_url + self.tts_path, json={"text": text, "speaker": speaker, "speed": speed}, timeout=self.timeout)
        return self._save_response(response, target)

    def convert(self, source: Path, target: Path, speaker: str, pitch: int = 0) -> Path:
        with source.open("rb") as audio:
            response = httpx.post(self.base_url + self.convert_path, files={"audio": (source.name, audio, "audio/wav")}, data={"speaker": speaker, "pitch": str(pitch)}, timeout=self.timeout)
        return self._save_response(response, target)
