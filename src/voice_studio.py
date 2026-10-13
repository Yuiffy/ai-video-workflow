"""Loopback configuration and audition page for direct cloned TTS."""
from __future__ import annotations

import argparse
import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from .tts import (DEFAULT_SETTINGS, ROOT, SpeechError, list_voices, load_settings,
                  public_settings, save_settings, synthesize)


def create_server(settings_path: Path = DEFAULT_SETTINGS, port: int = 7899):
    token = secrets.token_urlsafe(32)
    settings_lock = threading.Lock()
    synthesis_lock = threading.Lock()
    jobs: dict[str, dict] = {}
    output = settings_path.parent / "audio"
    output.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, data, kind="application/json; charset=utf-8"):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def trusted(self, write=False):
            address = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != address:
                self.reply(403, {"error": "请通过本机 127.0.0.1 地址访问。"})
                return False
            if write and (self.headers.get("Origin") not in {None, "http://" + address} or
                          not secrets.compare_digest(self.headers.get("X-Studio-Token", ""), token)):
                self.reply(403, {"error": "页面会话已过期，请刷新本机页面。"})
                return False
            return True

        def do_GET(self):
            if not self.trusted():
                return
            if self.path == "/":
                html = (ROOT / "src/voice_studio.html").read_text(encoding="utf-8").replace("__TOKEN__", token)
                return self.reply(200, html.encode(), "text/html; charset=utf-8")
            if self.path in {"/studio.js", "/studio.css"}:
                extension = self.path.rsplit(".", 1)[1]
                content = (ROOT / f"src/voice_studio.{extension}").read_bytes()
                return self.reply(200, content, "text/javascript; charset=utf-8" if extension == "js" else "text/css; charset=utf-8")
            if self.path == "/api/settings":
                with settings_lock:
                    return self.reply(200, public_settings(load_settings(settings_path)))
            if self.path == "/favicon.ico":
                return self.reply(204, b"", "image/x-icon")
            if re.fullmatch(r"/api/jobs/[a-f0-9]{32}", self.path):
                job = jobs.get(self.path.rsplit("/", 1)[1])
                return self.reply(200 if job else 404, job or {"error": "没有此任务。"})
            if re.fullmatch(r"/audio/[a-f0-9]{32}\.wav", self.path):
                file = output / self.path.rsplit("/", 1)[1]
                if file.is_file():
                    return self.reply(200, file.read_bytes(), "audio/wav")
            self.reply(404, {"error": "页面不存在。"})

        def do_POST(self):
            if not self.trusted(write=True):
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self.reply(415, {"error": "需要 JSON 请求。"})
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 128 * 1024:
                    return self.reply(413, {"error": "请求过大。"})
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("请求格式不正确。")
                if self.path == "/api/settings":
                    with settings_lock:
                        result = save_settings(payload, settings_path)
                    return self.reply(200, result)
                with settings_lock:
                    settings = load_settings(settings_path)
                if self.path == "/api/voices":
                    return self.reply(200, {"voices": list_voices(settings)})
                if self.path == "/api/synthesize":
                    text = payload.get("text", "")
                    if not isinstance(text, str) or not text.strip() or len(text) > 3000:
                        raise ValueError("请输入 1–3000 字符。")
                    provider = payload.get("provider", settings["provider"])
                    if provider not in {"minimax", "index", "cosy", "fish"}:
                        raise ValueError("未知引擎。")
                    if not synthesis_lock.acquire(blocking=False):
                        return self.reply(409, {"error": "已有一条语音正在生成，请等待完成。"})
                    job_id = uuid4().hex
                    jobs[job_id] = {"status": "running", "provider": provider}

                    def generate():
                        try:
                            result = synthesize(text, output / f"{job_id}.wav", settings, provider)
                            jobs[job_id] = {"status": "done", "audio": f"/audio/{job_id}.wav", **result}
                        except (SpeechError, ValueError) as exc:
                            jobs[job_id] = {"status": "error", "error": str(exc)}
                        except Exception:
                            jobs[job_id] = {"status": "error", "error": "生成失败，未自动重试。请检查本地环境或平台账户。"}
                        finally:
                            synthesis_lock.release()

                    threading.Thread(target=generate, daemon=True).start()
                    return self.reply(202, {"job_id": job_id})
                self.reply(404, {"error": "接口不存在。"})
            except (SpeechError, ValueError, TypeError) as exc:
                self.reply(400, {"error": str(exc) if not isinstance(exc, (TypeError, json.JSONDecodeError)) else "请求格式不正确。"})
            except Exception:
                self.reply(500, {"error": "操作失败，请检查本地配置文件权限。"})

        def log_message(self, format, *args):
            # No headers, request bodies, prompts or secrets in console logs.
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    parser.add_argument("--port", type=int, default=7899)
    args = parser.parse_args()
    server = create_server(args.settings.resolve(), args.port)
    print(f"Voice studio: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
