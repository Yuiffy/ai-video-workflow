"""Loopback MP3 bridge for Re:TTSCat using resident SAPI + RVC.

Run this with the configured RVC Python runtime. Model loading and HuBERT
initialization happen once; each request synthesizes, converts and encodes MP3
inside this process. WAV decoding and resampling also stay in-process, so a
request never starts an FFmpeg child process or its Windows console host.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
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
DEFAULT_INDEX_SAMPLE_SIZE = 65536


class CachedFaissIndex:
    """Keep the RVC retrieval index resident instead of rebuilding it per request."""

    def __init__(self, index, vectors):
        self._index = index
        self._vectors = vectors

    def reconstruct_n(self, start: int, count: int):
        if start == 0 and count == self._index.ntotal:
            return self._vectors
        return self._index.reconstruct_n(start, count)

    def __getattr__(self, name: str):
        return getattr(self._index, name)


def start_parent_watchdog(parent_pid: int) -> None:
    if os.name != "nt":
        return

    def watch() -> None:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        synchronize = 0x00100000
        while True:
            handle = kernel32.OpenProcess(synchronize, False, parent_pid)
            if not handle:
                os._exit(0)
            result = kernel32.WaitForSingleObject(handle, 2000)
            kernel32.CloseHandle(handle)
            if result == 0:
                os._exit(0)

    threading.Thread(target=watch, name="parent-watchdog", daemon=True).start()


class Engine:
    def __init__(self, config: dict, cache_dir: Path):
        self.config = config
        self.cache_dir = cache_dir.resolve()
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.error: str | None = None
        self.model_name = str(config["model"])
        self.original_index_path = str(config.get("index", ""))
        self.index_path = self.original_index_path
        self.index_sample_size = int(
            os.environ.get(
                "DANMAKU_RVC_INDEX_SAMPLE_SIZE",
                config.get("index_sample_size", DEFAULT_INDEX_SAMPLE_SIZE),
            )
        )
        self.pitch = int(config.get("pitch", 0))
        self.f0_method = str(config.get("f0_method", "pm"))
        self.index_rate = float(config.get("index_rate", 0.75))
        self.protect = float(config.get("protect", 0.33))
        self.sapi_voice = str(config.get("tts_voice", "Microsoft Huihui"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        threading.Thread(target=self._load, name="rvc-loader", daemon=True).start()

    def _prepare_index(self, np, faiss) -> tuple[str, object | None]:
        source_path = Path(self.original_index_path)
        if not self.original_index_path or not source_path.is_file():
            return "", None
        stat = source_path.stat()
        fingerprint = hashlib.sha256(
            (
                f"compact-l2-fp16-v1|{source_path.resolve()}|{stat.st_size}|"
                f"{stat.st_mtime_ns}|{self.index_sample_size}"
            ).encode()
        ).hexdigest()[:16]
        cache_dir = self.cache_dir / "indexes"
        cache_dir.mkdir(parents=True, exist_ok=True)
        compact_path = cache_dir / f"{fingerprint}.index"
        vectors_path = cache_dir / f"{fingerprint}.npy"

        index = None
        vectors = None
        if compact_path.is_file() and vectors_path.is_file():
            try:
                index = faiss.read_index(str(compact_path))
                vectors = np.load(vectors_path, mmap_mode="r")
                if index.ntotal != vectors.shape[0]:
                    raise ValueError("cached index and vectors do not match")
            except Exception:
                index = None
                vectors = None

        if index is None or vectors is None:
            started = time.monotonic()
            source = faiss.read_index(str(source_path))
            ntotal = int(source.ntotal)
            if ntotal > self.index_sample_size:
                positions = np.linspace(
                    0,
                    ntotal - 1,
                    self.index_sample_size,
                    dtype=np.int64,
                )
                source_vectors = source.reconstruct_n(0, ntotal)
                sampled = np.ascontiguousarray(source_vectors[positions], dtype=np.float32)
                del source_vectors
            else:
                sampled = np.ascontiguousarray(
                    source.reconstruct_n(0, ntotal),
                    dtype=np.float32,
                )
            index = faiss.IndexFlatL2(int(source.d))
            index.add(sampled)
            vectors = np.ascontiguousarray(sampled, dtype=np.float16)
            index_tmp = compact_path.with_suffix(".index.tmp")
            vectors_tmp = vectors_path.with_suffix(".npy.tmp")
            faiss.write_index(index, str(index_tmp))
            with vectors_tmp.open("wb") as handle:
                np.save(handle, vectors)
            index_tmp.replace(compact_path)
            vectors_tmp.replace(vectors_path)
            del source, sampled
            gc.collect()
            print(
                f"prepared compact RVC index {ntotal}->{index.ntotal} "
                f"in {time.monotonic() - started:.1f}s",
                flush=True,
            )

        faiss_read_index = faiss.read_index
        compact_resolved = compact_path.resolve()

        def read_cached_index(path, *args, **kwargs):
            if Path(path).resolve() == compact_resolved:
                return CachedFaissIndex(index, vectors)
            return faiss_read_index(path, *args, **kwargs)

        faiss.read_index = read_cached_index
        return str(compact_path), CachedFaissIndex(index, vectors)

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
            import faiss
            import soundfile as sf
            import torch
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
            runtime_index_path, cached_index = self._prepare_index(np, faiss)
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
                "load_audio": self._load_audio,
                "pipeline": pipeline,
                "hubert": hubert,
                "net_g": net_g,
                "target_sr": target_sr,
                "device": device,
                "use_f0": use_f0,
                "version": version,
                "cached_index": cached_index,
            }
            self.index_path = runtime_index_path

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

    @staticmethod
    def _load_audio(path: str, sr: int = 16000):
        import numpy as np
        import soundfile as sf
        from scipy.signal import resample_poly

        audio, source_sr = sf.read(
            str(path),
            dtype="float32",
            always_2d=True,
        )
        if audio.shape[1] > 1:
            audio = audio.mean(axis=1)
        else:
            audio = audio[:, 0]
        if source_sr != sr:
            gcd = math.gcd(int(source_sr), int(sr))
            audio = resample_poly(
                audio,
                int(sr) // gcd,
                int(source_sr) // gcd,
            )
        return np.ascontiguousarray(audio, dtype=np.float32)

    def _sapi(self, text: str, speed: float, target: Path) -> None:
        import pythoncom
        import win32com.client

        rate = max(-10, min(10, round((speed - 1.0) * 10)))
        pythoncom.CoInitialize()
        stream = None
        try:
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            matches = [
                token
                for token in voice.GetVoices()
                if self.sapi_voice in token.GetDescription()
            ]
            if not matches:
                raise RuntimeError(f"SAPI voice is not installed: {self.sapi_voice}")
            voice.Voice = matches[0]
            voice.Rate = rate
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            target.parent.mkdir(parents=True, exist_ok=True)
            stream.Open(str(target), 3, False)
            voice.AudioOutputStream = stream
            voice.Speak(text)
            stream.Close()
            stream = None
        finally:
            if stream is not None:
                stream.Close()
            pythoncom.CoUninitialize()
        if not target.is_file() or target.stat().st_size <= 44:
            raise RuntimeError("SAPI synthesis produced no audio")

    def _convert(self, source: Path):
        state = self.engine_state
        np = state["np"]
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
        return converted

    def _render(
        self,
        text: str,
        speed: float,
        raw: Path,
        output: Path,
    ) -> tuple[float, float, float]:
        started = time.monotonic()
        self._sapi(text, speed, raw)
        sapi_elapsed = time.monotonic() - started
        started = time.monotonic()
        converted = self._convert(raw)
        rvc_elapsed = time.monotonic() - started
        started = time.monotonic()
        self.engine_state["sf"].write(
            output,
            converted,
            self.engine_state["target_sr"],
            format="MP3",
            subtype="MPEG_LAYER_III",
        )
        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError("MP3 encoding produced no audio")
        return sapi_elapsed, rvc_elapsed, time.monotonic() - started

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
                    stages = self._render(text, speed, raw, output)
                finally:
                    self.pitch = old_pitch
                data = output.read_bytes()
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(cache_path)
            print(
                f"rendered elapsed_seconds={time.monotonic() - started:.2f} "
                f"sapi={stages[0]:.2f} rvc={stages[1]:.2f} mp3={stages[2]:.2f}",
                flush=True,
            )
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
            model_name = Path(engine.model_name).stem
            payload = {"status": status, "engine": f"SAPI + RVC {model_name}"}
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--port", type=int, default=7910)
    parser.add_argument("--parent-pid", type=int)
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
    engine = Engine(rvc_config, args.cache)
    server = Server(("127.0.0.1", args.port), engine)
    if args.parent_pid:
        start_parent_watchdog(args.parent_pid)
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
