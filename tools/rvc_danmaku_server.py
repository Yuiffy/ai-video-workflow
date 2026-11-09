"""Loopback MP3 bridge for Re:TTSCat using resident SAPI + suiV2 RVC.

Run this with the configured RVC Python runtime. Model loading and HuBERT
initialization happen once; each request only synthesizes, converts and encodes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_CACHE = ROOT / "outputs/danmaku-tts/cache"
SAPI_SCRIPT = ROOT / "tools/sapi_tts.py"


def hidden_process_options() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


class Engine:
    def __init__(self, config: dict, cache_dir: Path, ffmpeg: str):
        self.config = config
        self.cache_dir = cache_dir.resolve()
        self.ffmpeg = ffmpeg
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.error: str | None = None
        self.model_name = str(config["model"])
        self.index_path = str(config.get("index", ""))
        self.pitch = int(config.get("pitch", 0))
        self.f0_method = str(config.get("f0_method", "pm"))
        self.index_rate = float(config.get("index_rate", 0.75))
        self.protect = float(config.get("protect", 0.33))
        self.sapi_voice = str(config.get("tts_voice", "Microsoft Huihui"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        threading.Thread(target=self._load, name="rvc-loader", daemon=True).start()

    def _load(self) -> None:
        try:
            root = Path(self.config["rvc_root"]).resolve()
            runtime = Path(self.config["runtime_python"]).resolve()
            if not runtime.is_file():
                raise FileNotFoundError(f"RVC runtime not found: {runtime}")
            os.chdir(root)
            sys.path.insert(0, str(root))
            os.environ.setdefault("weight_root", str(root / "assets" / "weights"))
            os.environ.setdefault("rmvpe_root", str(root / "assets" / "rmvpe"))

            import numpy as np
            import soundfile as sf
            import torch
            from infer.lib.audio import load_audio
            from infer.lib.infer_pack.models import (
                SynthesizerTrnMs256NSFsid,
                SynthesizerTrnMs256NSFsid_nono,
                SynthesizerTrnMs768NSFsid,
                SynthesizerTrnMs768NSFsid_nono,
            )
            from infer.modules.vc.pipeline import Pipeline
            from infer.modules.vc.utils import load_hubert

            started = time.monotonic()
            device = "cuda" if torch.cuda.is_available() else "cpu"
            is_half = device == "cuda"
            model_path = Path(self.model_name)
            if not model_path.is_absolute():
                model_path = root / "assets" / "weights" / model_path
            checkpoint = torch.load(model_path, map_location="cpu")
            target_sr = checkpoint["config"][-1]
            checkpoint["config"][-3] = checkpoint["weight"]["emb_g.weight"].shape[0]
            use_f0 = checkpoint.get("f0", 1)
            version = checkpoint.get("version", "v1")
            model_class = {
                ("v1", 1): SynthesizerTrnMs256NSFsid,
                ("v2", 1): SynthesizerTrnMs768NSFsid,
                ("v1", 0): SynthesizerTrnMs256NSFsid_nono,
                ("v2", 0): SynthesizerTrnMs768NSFsid_nono,
            }[(version, use_f0)]
            net_g = (
                model_class(*checkpoint["config"], is_half=is_half)
                if use_f0
                else model_class(*checkpoint["config"])
            )
            del net_g.enc_q
            net_g.load_state_dict(checkpoint["weight"], strict=False)
            net_g.eval().to(device)
            net_g = net_g.half() if is_half else net_g.float()

            class RvcConfig:
                x_pad, x_query, x_center, x_max = 3, 10, 60, 180

            rvc_config = RvcConfig()
            rvc_config.is_half = is_half
            rvc_config.device = device
            hubert = load_hubert(rvc_config)
            pipeline = Pipeline(target_sr, rvc_config)
            self.engine_state = {
                "np": np,
                "sf": sf,
                "torch": torch,
                "load_audio": load_audio,
                "pipeline": pipeline,
                "hubert": hubert,
                "net_g": net_g,
                "target_sr": target_sr,
                "device": device,
                "use_f0": use_f0,
                "version": version,
            }

            with tempfile.TemporaryDirectory(prefix="danmaku-rvc-warmup-") as directory:
                warm_raw = Path(directory) / "raw.wav"
                warm_out = Path(directory) / "output.mp3"
                self._render("你好。", 1.0, warm_raw, warm_out)
            print(
                f"engine ready in {time.monotonic() - started:.1f}s; model={model_path.name}",
                flush=True,
            )
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            print(f"engine failed: {self.error}", file=sys.stderr, flush=True)
        finally:
            self.ready.set()

    def _sapi(self, text: str, speed: float, target: Path) -> None:
        rate = max(-10, min(10, round((speed - 1.0) * 10)))
        result = subprocess.run(
            [
                sys.executable,
                str(SAPI_SCRIPT),
                "--voice",
                self.sapi_voice,
                "--text",
                text,
                "--rate",
                str(rate),
                "--output",
                str(target),
            ],
            capture_output=True,
            timeout=30,
            **hidden_process_options(),
        )
        if result.returncode or not target.is_file() or target.stat().st_size <= 44:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"SAPI synthesis failed: {detail}")

    def _convert(self, source: Path, target: Path) -> None:
        state = self.engine_state
        np = state["np"]
        sf = state["sf"]
        torch = state["torch"]
        audio = state["load_audio"](str(source), 16000)
        peak = np.abs(audio).max() / 0.95
        if peak > 1:
            audio /= peak
        index = self.index_path if self.index_path and Path(self.index_path).is_file() else ""
        with torch.no_grad():
            converted = state["pipeline"].pipeline(
                state["hubert"],
                state["net_g"],
                0,
                audio,
                str(source),
                [0, 0, 0],
                self.pitch,
                self.f0_method,
                index,
                self.index_rate,
                state["use_f0"],
                3,
                state["target_sr"],
                0,
                1.0,
                state["version"],
                self.protect,
                None,
            )
        sf.write(target, converted, state["target_sr"])

    def _encode_mp3(self, source: Path, target: Path) -> None:
        result = subprocess.run(
            [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "128k",
                str(target),
            ],
            capture_output=True,
            timeout=60,
            **hidden_process_options(),
        )
        if result.returncode or not target.is_file() or target.stat().st_size <= 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ffmpeg MP3 encoding failed: {detail}")

    def _render(self, text: str, speed: float, raw: Path, output: Path) -> None:
        converted = raw.with_name(raw.stem + "-converted.wav")
        self._sapi(text, speed, raw)
        self._convert(raw, converted)
        self._encode_mp3(converted, output)

    def speak(self, text: str, speed: float, pitch: int | None) -> bytes:
        if not self.ready.wait(timeout=300):
            raise TimeoutError("RVC engine did not become ready")
        if self.error:
            raise RuntimeError(self.error)
        pitch = self.pitch if pitch is None else pitch
        index_fingerprint = ""
        if self.index_path and Path(self.index_path).is_file():
            stat = Path(self.index_path).stat()
            index_fingerprint = f"{stat.st_size}:{stat.st_mtime_ns}"
        key_data = json.dumps(
            {
                "text": text,
                "speed": speed,
                "model": self.model_name,
                "index": index_fingerprint,
                "pitch": pitch,
                "f0_method": self.f0_method,
                "index_rate": self.index_rate,
                "protect": self.protect,
                "voice": self.sapi_voice,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        cache_path = self.cache_dir / (hashlib.sha256(key_data.encode()).hexdigest() + ".mp3")
        with self.lock:
            if cache_path.is_file() and cache_path.stat().st_size > 0:
                return cache_path.read_bytes()
            started = time.monotonic()
            with tempfile.TemporaryDirectory(prefix="danmaku-rvc-") as directory:
                raw = Path(directory) / "raw.wav"
                output = Path(directory) / "output.mp3"
                old_pitch = self.pitch
                self.pitch = pitch
                try:
                    self._render(text, speed, raw, output)
                finally:
                    self.pitch = old_pitch
                data = output.read_bytes()
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(cache_path)
            print(f"rendered elapsed_seconds={time.monotonic() - started:.2f}", flush=True)
            return data


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, engine: Engine):
        self.engine = engine
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server: Server
    server_version = "DanmakuRVC/1.0"

    def reply(self, status: int, content_type: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def reply_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.reply(status, "application/json; charset=utf-8", data)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            engine = self.server.engine
            status = "ready" if engine.ready.is_set() and not engine.error else "loading"
            if engine.error:
                status = "error"
            payload = {"status": status, "engine": "SAPI + RVC suiV2"}
            if engine.error:
                payload["error"] = engine.error
            self.reply_json(200 if status == "ready" else 503, payload)
            return
        if parsed.path != "/tts":
            self.reply_json(404, {"error": "not found"})
            return

        query = parse_qs(parsed.query)
        text = query.get("text", [""])[0].strip()
        if not text or len(text) > 1000:
            self.reply_json(400, {"error": "text must contain 1-1000 characters"})
            return
        try:
            speed = float(query.get("speed", ["1.0"])[0])
            if not 0.5 <= speed <= 1.5:
                raise ValueError
        except ValueError:
            self.reply_json(400, {"error": "speed must be between 0.5 and 1.5"})
            return
        try:
            pitch = int(query["pitch"][0]) if "pitch" in query else None
            if pitch is not None and not -24 <= pitch <= 24:
                raise ValueError
        except ValueError:
            self.reply_json(400, {"error": "pitch must be between -24 and 24"})
            return
        try:
            audio = self.server.engine.speak(text, speed, pitch)
        except Exception as exc:
            self.reply_json(500, {"error": str(exc)})
            return
        self.reply(200, "audio/mpeg", audio)

    def log_request(self, code="-", size="-") -> None:
        route = urlsplit(self.path).path
        print(f"{self.command} {route} {code} {size}", flush=True)

    def log_message(self, format, *args) -> None:
        return


def read_ffmpeg(config: dict) -> str:
    value = str(config.get("ffmpeg_bin", "ffmpeg"))
    found = shutil.which(value)
    if not found:
        raise FileNotFoundError(f"ffmpeg not found: {value}")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--port", type=int, default=7910)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise ValueError("invalid port")
    full_config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    rvc_config = full_config["rvc"]
    for field, env_name in (
        ("model", "DANMAKU_RVC_MODEL"),
        ("index", "DANMAKU_RVC_INDEX"),
        ("pitch", "DANMAKU_RVC_PITCH"),
    ):
        if os.environ.get(env_name):
            rvc_config[field] = os.environ[env_name]
    engine = Engine(rvc_config, args.cache, read_ffmpeg(full_config))
    server = Server(("127.0.0.1", args.port), engine)
    engine.start()
    print(f"Danmaku RVC listening on http://127.0.0.1:{args.port}/tts", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
