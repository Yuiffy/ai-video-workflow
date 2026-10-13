"""Direct cloned speech via cloud or isolated local model runtimes."""
from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import subprocess
import tempfile
from pathlib import Path

import httpx

from .storage import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS = ROOT / "outputs/voice-studio/settings.json"
MINIMAX_URL = "https://api.minimax.cn/v1/"
DEFAULTS = {"provider": "cosy", "model": "speech-2.8-hd", "voice_id": "",
            "speed": 1.0, "emotion": "", "index_root": "", "reference_audio": "",
            "cosy_root": "", "cosy_reference_audio": "", "cosy_reference_text": "",
            "cosy_text_frontend": True, "fish_root": "", "fish_reference_audio": "",
            "fish_reference_text": ""}


class SpeechError(RuntimeError):
    pass


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
    fn.restype = ctypes.c_int
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise SpeechError("Windows 无法读取或保存密钥，请使用保存密钥时的 Windows 账户。")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def load_settings(path: Path = DEFAULT_SETTINGS) -> dict:
    return {**DEFAULTS, **(read_json(path) if path.exists() else {})}


def save_settings(updates: dict, path: Path = DEFAULT_SETTINGS) -> dict:
    settings = load_settings(path)
    for field in DEFAULTS:
        if field in updates:
            settings[field] = updates[field]
    if settings["provider"] not in {"minimax", "index", "cosy", "fish"}:
        raise ValueError("请选择 MiniMax、IndexTTS、CosyVoice 或 Fish Speech。")
    if not isinstance(settings["cosy_text_frontend"], bool):
        raise ValueError("文本规范化设置必须为布尔值。")
    if settings["model"] not in {"speech-2.8-hd", "speech-2.8-turbo"}:
        raise ValueError("请选择支持的 MiniMax 模型。")
    settings["speed"] = float(settings["speed"])
    if not 0.5 <= settings["speed"] <= 2:
        raise ValueError("语速范围为 0.5–2。")
    if settings["emotion"] not in {"", "happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm"}:
        raise ValueError("不支持的情绪。")
    for field in ("voice_id", "index_root", "reference_audio", "cosy_root", "cosy_reference_audio", "cosy_reference_text",
                  "fish_root", "fish_reference_audio", "fish_reference_text"):
        if not isinstance(settings[field], str) or len(settings[field]) > 2048:
            raise ValueError("配置字段格式不正确。")
        settings[field] = settings[field].strip()
    api_key = updates.get("api_key", "")
    if not isinstance(api_key, str) or len(api_key) > 16384:
        raise ValueError("API Key 格式不正确。")
    api_key = api_key.strip()
    if api_key:
        if any(c.isspace() for c in api_key):
            raise ValueError("API Key 中不能有空格或换行。")
        if os.name != "nt":
            raise SpeechError("此配置页使用 Windows 加密；其他系统请通过 MINIMAX_API_KEY 环境变量配置。")
        settings["api_key_dpapi"] = base64.b64encode(_dpapi(api_key.encode())).decode()
    if updates.get("clear_key") is True:
        settings.pop("api_key_dpapi", None)
    write_json(path, settings)
    return public_settings(settings)


def public_settings(settings: dict) -> dict:
    result = {k: settings[k] for k in DEFAULTS}
    result["has_key"] = bool(settings.get("api_key_dpapi") or os.environ.get("MINIMAX_API_KEY"))
    result["local_engines"] = {}
    for provider, config in (("index", "checkpoints/config.yaml"),
                             ("cosy", "pretrained_models/Fun-CosyVoice3-0.5B/cosyvoice3.yaml"),
                             ("fish", "checkpoints/s2-pro/model.safetensors.index.json")):
        value = settings[provider + "_root"]
        root = Path(value)
        result["local_engines"][provider] = bool(value and
            (root / ".venv/Scripts/python.exe").is_file() and
            (root / config).is_file() and (root / "workflow-verified.json").is_file())
    result["local_installed"] = result["local_engines"].get(settings["provider"], False)
    return result


def api_key(settings: dict) -> str:
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if key:
        return key
    encrypted = settings.get("api_key_dpapi")
    if not encrypted:
        raise SpeechError("请先保存 MiniMax API Key。")
    return _dpapi(base64.b64decode(encrypted), decrypt=True).decode()


def minimax_request(endpoint: str, payload: dict, settings: dict) -> dict:
    # Fixed first-party destination, no redirects or automatic paid retries.
    try:
        with httpx.Client(timeout=180, follow_redirects=False) as client:
            response = client.post(MINIMAX_URL + endpoint, json=payload,
                                   headers={"Authorization": "Bearer " + api_key(settings)})
        if response.status_code != 200:
            raise SpeechError(f"MiniMax HTTP {response.status_code}；请检查 API Key、余额及网络。")
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SpeechError("MiniMax 请求未成功返回；未自动重试，请检查账户记录后再决定是否重试。") from exc
    status = data.get("base_resp", {}).get("status_code")
    if status != 0:
        raise SpeechError(f"MiniMax 返回错误码 {status}；请检查账户与音色 ID。")
    return data


def list_voices(settings: dict) -> list[dict]:
    response = minimax_request("get_voice", {"voice_type": "all"}, settings)
    return [{"id": voice["voice_id"], "name": voice.get("voice_name") or voice["voice_id"], "kind": kind}
            for kind in ("voice_cloning", "voice_generation", "system_voice")
            for voice in response.get(kind, []) if voice.get("voice_id")]


def synthesize(text: str, target: Path, settings: dict, provider: str | None = None) -> dict:
    if not isinstance(text, str) or not text.strip() or len(text) > 3000:
        raise ValueError("每次请输入 1–3000 字符。长稿请按段生成。")
    if not 0.5 <= float(settings["speed"]) <= 2:
        raise ValueError("直接 TTS 的语速范围为 0.5–2。")
    provider = provider or settings["provider"]
    if provider == "fish":
        if len(text) > 300:
            raise ValueError("Fish Speech 本地模式每段最多 300 字符，请将长稿分段生成。")
        if float(settings["speed"]) != 1.0:
            raise ValueError("Fish Speech 当前支持原速 1.0；可在文案中使用语气标签。")
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if provider == "minimax":
        if not settings["voice_id"]:
            raise SpeechError("请先选择音色，或填入开放平台的 voice_id。")
        voice = {"voice_id": settings["voice_id"], "speed": settings["speed"], "vol": 1, "pitch": 0}
        if settings["emotion"]:
            voice["emotion"] = settings["emotion"]
        response = minimax_request("t2a_v2", {
            "model": settings["model"], "text": text, "stream": False,
            "voice_setting": voice, "language_boost": "auto", "output_format": "hex",
            "audio_setting": {"sample_rate": 32000, "format": "wav", "channel": 1},
        }, settings)
        try:
            audio = bytes.fromhex(response["data"]["audio"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SpeechError("MiniMax 未返回有效音频；未自动重试。") from exc
        if audio[:4] != b"RIFF" or len(audio) <= 44:
            raise SpeechError("MiniMax 返回的音频不是有效 WAV。")
        target.write_bytes(audio)
        return {"provider": provider, "model": settings["model"], "trace_id": response.get("trace_id"),
                "usage_characters": response.get("extra_info", {}).get("usage_characters")}
    if provider not in {"index", "cosy", "fish"}:
        raise ValueError("未知配音引擎。")
    label = {"cosy": "CosyVoice 3", "index": "IndexTTS", "fish": "Fish Speech S2 Pro"}[provider]
    root_value = settings[provider + "_root"]
    root = Path(root_value).resolve()
    runtime = root / ".venv/Scripts/python.exe"
    reference_value = settings[provider + "_reference_audio" if provider in {"cosy", "fish"} else "reference_audio"]
    reference = Path(reference_value)
    if not root_value or not runtime.is_file():
        raise SpeechError(f"{label} 本地环境尚未安装完成。")
    if not reference_value or not reference.is_file():
        raise SpeechError("请选择本地音色参考音频。")
    reference_text = settings.get(provider + "_reference_text", "")
    if provider in {"cosy", "fish"} and not reference_text.strip():
        raise SpeechError(f"请填写与 {label} 参考音频对应的文字。")
    with tempfile.TemporaryDirectory(prefix=provider + "-tts-") as directory:
        request = Path(directory) / "request.json"
        write_json(request, {"text": text, "reference": str(reference.resolve()),
                             "output": str(target), "speed": settings["speed"],
                             "reference_text": reference_text,
                             "text_frontend": settings.get("cosy_text_frontend", True),
                             **({"max_length": 4096, "max_new_tokens": 2048,
                                 "report": str(target.with_suffix(".fish.json")),
                                 "seed": 42, "temperature": 0.8, "top_p": 0.9} if provider == "fish" else {})})
        # The worker runs in the isolated upstream environment and frees GPU on exit.
        log = target.with_suffix(".log")
        with log.open("w", encoding="utf-8") as stream:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1", "PYTHONPATH": str(root),
                   "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
            try:
                worker = {"cosy": "cosy_tts_worker.py", "index": "index_tts_worker.py",
                          "fish": "fish_tts_worker.py"}[provider]
                result = subprocess.run([str(runtime), str(ROOT / "tools" / worker),
                                         "--request", str(request)], cwd=root, env=env,
                                        stdout=stream, stderr=subprocess.STDOUT, timeout=1800)
            except subprocess.TimeoutExpired as exc:
                raise SpeechError(f"{label} 生成超时，进程已停止。") from exc
        if result.returncode or not target.is_file():
            raise SpeechError(f"{label} 生成失败，请检查本地输出目录中的同名日志。")
    return {"provider": provider, "model": {"cosy": "Fun-CosyVoice3-0.5B-2512",
                                            "index": "IndexTTS-2.5", "fish": "Fish Audio S2 Pro"}[provider]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    parser.add_argument("--provider", choices=["minimax", "index", "cosy", "fish"])
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = synthesize(args.text, args.output, load_settings(args.settings), args.provider)
    print(json.dumps({"output": str(args.output), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
