"""Loopback-only TTS/RVC HTTP bridge; no WebUI or model-runtime modifications."""
from __future__ import annotations

import argparse
import base64
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .rvc_client import RvcClient
from .storage import read_json


def create_server(config: dict, port: int = 7898) -> ThreadingHTTPServer:
    config = {**config, "mode": "command"}
    client = RvcClient(config)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/health":
                self.send_error(404)
                return
            payload = json.dumps({"status": "ready", "engine": "TTS + RVC",
                                  "model": config.get("model"), "busy": lock.locked()}).encode()
            self.reply(200, "application/json", payload)

        def reply(self, code, content_type, data):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path not in {"/api/tts", "/api/convert"}:
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 50 * 1024 * 1024:
                    self.send_error(413)
                    return
                payload = json.loads(self.rfile.read(size))
                with lock, tempfile.TemporaryDirectory(prefix="video-voice-") as directory:
                    target = Path(directory) / "output.wav"
                    if self.path == "/api/tts":
                        text = payload.get("text", "")
                        if not isinstance(text, str) or not 0 < len(text) <= 10000:
                            raise ValueError("text must contain 1–10000 characters")
                        client.tts(text, target, float(payload.get("speed", 1)))
                    else:
                        source = Path(directory) / "input.audio"
                        source.write_bytes(base64.b64decode(payload["audio_base64"], validate=True))
                        pitch = int(payload.get("pitch", config.get("pitch", 0)))
                        if not -24 <= pitch <= 24:
                            raise ValueError("pitch must be between -24 and 24")
                        client.convert(source, target, pitch)
                    data = target.read_bytes()
                    if data[:4] != b"RIFF":
                        raise ValueError("Configured command must produce WAV")
                self.reply(200, "audio/wav", data)
            except (ValueError, KeyError) as exc:
                self.reply(400, "application/json", json.dumps({"error": str(exc)}).encode())
            except Exception as exc:
                self.reply(500, "application/json", json.dumps({"error": str(exc)}).encode())

        def log_message(self, format, *args):
            # Log endpoint and result only; no text or audio content.
            print(format % args, flush=True)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--port", type=int, default=7898)
    args = parser.parse_args()
    server = create_server(read_json(args.config)["rvc"], args.port)
    print(f"Local voice service: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
