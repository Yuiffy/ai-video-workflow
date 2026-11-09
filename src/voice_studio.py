"""Loopback configuration and audition page for direct cloned TTS."""
from __future__ import annotations

import argparse
import datetime
import json
import re
import secrets
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from .tts import (DEFAULT_SETTINGS, ROOT, SpeechError, list_voices, load_settings,
                  public_settings, save_settings, synthesize)

TTS_CANDIDATES = [
    {
        "id": "rvc-v2-p5",
        "name": "岁己 RVC v2 +5",
        "kind": "RVC 变声",
        "summary": "上一版弹幕声线，使用 SAPI 起句和 suiV2；保留作听感对照。",
        "fit": "归档对照",
        "latency": "热请求约 1.3–2.0 秒",
        "memory": "约 0.7–0.9 GiB 显存",
        "quality": "已认可，+5 音高",
        "audio": "outputs/voice-studio/tts-choice/current-rvc.mp3",
        "tone": "上一版",
    },
    {
        "id": "rvc-v3-e10",
        "name": "岁己 RVC v3 · 当前",
        "kind": "RVC 变声",
        "summary": "当前弹幕声线；SAPI、RVC 和 MP3 编码都在常驻 worker 内完成。",
        "fit": "实时弹幕",
        "latency": "热请求约 1.6–2.1 秒；缓存命中低于 0.1 秒",
        "memory": "常驻索引约 0.3 GB；GPU 约 1 GiB",
        "quality": "相似度 0.7714 · CER 5.40%",
        "audio": "outputs/voice-studio/tts-choice/rvc-v3-danmaku.mp3",
        "tone": "当前",
    },
    {
        "id": "cosy",
        "name": "CosyVoice 3",
        "kind": "直接克隆 TTS",
        "summary": "从参考音频直接生成岁己声线，支持文本规范化和本地运行。",
        "fit": "离线旁白",
        "latency": "11.36 秒样例约 16.1 秒生成",
        "memory": "约 4.3 GiB 显存",
        "quality": "自然度基线",
        "audio": "outputs/voice-studio/style-ab-20261007/cosyvoice3/cosy-chat1-chat.wav",
        "tone": "自然",
    },
    {
        "id": "index",
        "name": "IndexTTS 2.5",
        "kind": "直接克隆 TTS",
        "summary": "音色参考和情绪控制分开，适合带明显情绪的口播。",
        "fit": "离线情绪口播",
        "latency": "加载加生成约 47.7 秒",
        "memory": "峰值约 5.59 GiB",
        "quality": "用户曾反馈部分鼻音与北方口音",
        "audio": "outputs/voice-studio/style-ab-20261007/cosyvoice3/index-chat1-chat.wav",
        "tone": "有情绪",
    },
    {
        "id": "fish",
        "name": "Fish Speech S2 Pro",
        "kind": "直接克隆 TTS",
        "summary": "直接克隆并支持 [excited]、[whisper] 等语气标签。",
        "fit": "离线高质量短段",
        "latency": "加载约 4 分钟；样例生成约 7.5 秒",
        "memory": "峰值约 9.19 GiB",
        "quality": "用户试听后感觉不错",
        "audio": "outputs/fish-speech-20261013/sui-emotion.wav",
        "tone": "表现力",
    },
    {
        "id": "minimax",
        "name": "MiniMax Speech 2.8 HD",
        "kind": "云端直接克隆",
        "summary": "已有网页克隆先例，API 支持情绪、语速和音色管理。",
        "fit": "快速生产对照",
        "latency": "取决于网络与队列",
        "memory": "不占本机显存",
        "quality": "HD 约 3.50 元 / 万计费字符",
        "audio": "",
        "tone": "省显存",
    },
    {
        "id": "voxcpm2",
        "name": "VoxCPM2",
        "kind": "直接克隆 TTS",
        "summary": "2B 本地模型，支持参考音频和带转写的续接式克隆。",
        "fit": "下一轮本地测试",
        "latency": "本机未安装",
        "memory": "官方列出约 8 GB",
        "quality": "尚无声线样例",
        "audio": "",
        "tone": "待验证",
    },
    {
        "id": "gpt-sovits",
        "name": "GPT-SoVITS",
        "kind": "定制训练 TTS",
        "summary": "少样本微调路线，适合把岁己音色与说话习惯长期固定下来。",
        "fit": "长期角色声线",
        "latency": "本机未安装",
        "memory": "随训练与推理配置变化",
        "quality": "需要高质量转写与训练",
        "audio": "",
        "tone": "长期方案",
    },
]


def create_server(settings_path: Path = DEFAULT_SETTINGS, port: int = 7899):
    token = secrets.token_urlsafe(32)
    settings_lock = threading.Lock()
    synthesis_lock = threading.Lock()
    jobs: dict[str, dict] = {}
    output = settings_path.parent / "audio"
    output.mkdir(parents=True, exist_ok=True)
    choice_path = settings_path.parent / "tts-choice.json"

    def choice_payload():
        selection = {}
        if choice_path.is_file():
            try:
                selection = json.loads(choice_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                selection = {}
        candidates = []
        for candidate in TTS_CANDIDATES:
            item = {key: value for key, value in candidate.items() if key != "audio"}
            audio_value = candidate["audio"]
            audio_path = ROOT / audio_value if audio_value else None
            item["audio_url"] = (
                f"/choice-audio/{candidate['id']}"
                if audio_path is not None and audio_path.is_file()
                else ""
            )
            candidates.append(item)
        return {
            "candidates": candidates,
            "selected": selection.get("selected", ""),
            "note": selection.get("note", ""),
            "saved_at": selection.get("saved_at", ""),
        }

    def danmaku_request(path: str, timeout: float = 5):
        request = urllib.request.Request(
            f"http://127.0.0.1:7910{path}",
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except (OSError, ValueError, urllib.error.URLError):
            return {"status": "offline"}

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
            if self.path in {"/tts-choice", "/tts-choice/"}:
                html = (ROOT / "src/tts_choice.html").read_text(encoding="utf-8").replace("__TOKEN__", token)
                return self.reply(200, html.encode(), "text/html; charset=utf-8")
            if self.path in {"/studio.js", "/studio.css"}:
                extension = self.path.rsplit(".", 1)[1]
                content = (ROOT / f"src/voice_studio.{extension}").read_bytes()
                return self.reply(200, content, "text/javascript; charset=utf-8" if extension == "js" else "text/css; charset=utf-8")
            if self.path in {"/tts-choice.js", "/tts-choice.css"}:
                extension = self.path.rsplit(".", 1)[1]
                content = (ROOT / f"src/tts_choice.{extension}").read_bytes()
                return self.reply(200, content, "text/javascript; charset=utf-8" if extension == "js" else "text/css; charset=utf-8")
            if self.path == "/api/settings":
                with settings_lock:
                    return self.reply(200, public_settings(load_settings(settings_path)))
            if self.path == "/api/tts-choice":
                return self.reply(200, choice_payload())
            if self.path == "/api/danmaku":
                return self.reply(200, danmaku_request("/health"))
            if self.path == "/favicon.ico":
                return self.reply(204, b"", "image/x-icon")
            if re.fullmatch(r"/api/jobs/[a-f0-9]{32}", self.path):
                job = jobs.get(self.path.rsplit("/", 1)[1])
                return self.reply(200 if job else 404, job or {"error": "没有此任务。"})
            if re.fullmatch(r"/audio/[a-f0-9]{32}\.wav", self.path):
                file = output / self.path.rsplit("/", 1)[1]
                if file.is_file():
                    return self.reply(200, file.read_bytes(), "audio/wav")
            choice_match = re.fullmatch(r"/choice-audio/([a-z0-9-]+)", self.path)
            if choice_match:
                candidate = next(
                    (item for item in TTS_CANDIDATES if item["id"] == choice_match[1]),
                    None,
                )
                if candidate and candidate["audio"]:
                    file = ROOT / candidate["audio"]
                    if file.is_file():
                        kind = "audio/mpeg" if file.suffix.lower() == ".mp3" else "audio/wav"
                        return self.reply(200, file.read_bytes(), kind)
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
                if self.path == "/api/tts-choice":
                    selected = payload.get("selected", "")
                    if selected not in {item["id"] for item in TTS_CANDIDATES}:
                        raise ValueError("请选择一个有效的声音方案。")
                    note = payload.get("note", "")
                    if not isinstance(note, str) or len(note) > 1000:
                        raise ValueError("备注不能超过 1000 字符。")
                    record = {
                        "selected": selected,
                        "note": note.strip(),
                        "saved_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                    }
                    choice_path.parent.mkdir(parents=True, exist_ok=True)
                    choice_path.write_text(
                        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    return self.reply(200, choice_payload())
                if self.path == "/api/danmaku":
                    action = payload.get("action", "status")
                    path = {"status": "/health", "warm": "/warm", "unload": "/unload"}.get(action)
                    if not path:
                        raise ValueError("未知的弹幕模型操作。")
                    result = danmaku_request(path)
                    return self.reply(200 if result.get("status") != "offline" else 503, result)
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
