"""TTS and RVC are separate steps; support local commands or the bundled service."""
from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

import httpx


class RvcError(RuntimeError):
    pass


class RvcClient:
    def __init__(self, config: dict):
        self.config = config
        self.mode = config.get("mode", "http")
        self.base_url = config.get("base_url", "http://127.0.0.1:7898").rstrip("/")
        self.timeout = config.get("timeout_seconds", 240)

    def _command(self, template: list[str], **overrides):
        root = Path(__file__).resolve().parents[1]
        values = {**self.config, "rvc_bridge": str(root / "tools/rvc_convert.py"),
                  "sapi_tts": str(root / "tools/sapi_tts.py"),
                  "runtime_python": self.config.get("runtime_python", sys.executable), **overrides}
        args = [str(value).format(**values) for value in template]
        result = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace",
                                timeout=self.timeout)
        if result.returncode:
            raise RvcError(result.stderr[-1600:])

    def _request(self, path: str, payload: dict, target: Path):
        with httpx.Client(timeout=self.timeout, trust_env=False) as client:
            response = client.post(self.base_url + path, json=payload)
            response.raise_for_status()
        if response.content[:4] != b"RIFF":
            raise RvcError("The local voice service must return WAV bytes")
        target.write_bytes(response.content)

    def tts(self, text: str, target: Path, speed: float = 1.0):
        target.parent.mkdir(parents=True, exist_ok=True)
        if self.mode == "http":
            self._request("/api/tts", {"text": text, "speed": speed}, target)
        else:
            if not self.config.get("tts_command"):
                raise RvcError("Configure a TTS command or use the local HTTP service")
            rate = round((speed - 1) * 10)
            self._command(self.config["tts_command"], text=text, output=str(target),
                          speed=speed, rate=rate)
        if not target.is_file() or target.stat().st_size <= 44:
            raise RvcError("TTS produced no audio")
        return target

    def convert(self, source: Path, target: Path, pitch: int | None = None):
        target.parent.mkdir(parents=True, exist_ok=True)
        pitch = self.config.get("pitch", 0) if pitch is None else pitch
        if self.mode == "http":
            self._request("/api/convert", {"audio_base64": base64.b64encode(source.read_bytes()).decode(),
                                          "pitch": pitch}, target)
        else:
            self._command(self.config["convert_command"], input=str(source.resolve()),
                          output=str(target.resolve()), pitch=pitch)
        if not target.is_file() or target.stat().st_size <= 44:
            raise RvcError("RVC produced no audio")
        return target
