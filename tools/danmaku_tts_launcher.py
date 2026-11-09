"""Start or control the danmaku TTS PM2 app without a console window."""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
ECOSYSTEM = ROOT / "ecosystem.danmaku-tts.config.cjs"
APP_NAME = "danmaku-tts"
DEFAULT_PORT = 7910
LOG_PATH = ROOT / "outputs/danmaku-tts/launcher.log"


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


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"{stamp} {message}\n")


def find_node() -> Path:
    candidates = [
        os.environ.get("NODE_EXE", ""),
        shutil.which("node") or "",
        str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs/node.exe"),
        str(
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
            / "nodejs/node.exe"
        ),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise FileNotFoundError("node.exe was not found")


def find_pm2_script() -> Path:
    candidates = [
        os.environ.get("PM2_JS", ""),
        str(Path.home() / "AppData/Roaming/npm/node_modules/pm2/bin/pm2"),
        str(Path.home() / "AppData/Local/pnpm/global/5/node_modules/pm2/bin/pm2"),
    ]
    local_pnpm = Path.home() / "AppData/Local/pnpm"
    candidates.extend(
        glob.glob(str(local_pnpm / "global/*/node_modules/pm2/bin/pm2"))
    )
    candidates.extend(
        glob.glob(
            str(
                local_pnpm
                / "global/5/.pnpm/pm2@*/node_modules/pm2/bin/pm2"
            )
        )
    )

    pm2_command = shutil.which("pm2")
    if pm2_command:
        command_path = Path(pm2_command)
        candidates.append(str(command_path))
        if command_path.suffix.lower() in {".cmd", ".bat"}:
            wrapper = command_path.read_text(encoding="utf-8", errors="replace")
            match = re.search(r'"([^"]*pm2[^"]*[\\/]bin[\\/]pm2)"', wrapper)
            if match:
                candidates.append(match.group(1))

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and path.name == "pm2":
            return path.resolve()
        if path.is_file() and path.suffix.lower() in {".cmd", ".bat"}:
            wrapper = path.read_text(encoding="utf-8", errors="replace")
            match = re.search(r'"([^"]*pm2[^"]*[\\/]bin[\\/]pm2)"', wrapper)
            if match and Path(match.group(1)).is_file():
                return Path(match.group(1)).resolve()
    raise FileNotFoundError("PM2 entry script was not found")


def pm2_environment() -> dict[str, str]:
    env = os.environ.copy()
    pm2_home = Path(
        env.get("DANMAKU_PM2_HOME", str(Path.home() / ".pm2"))
    ).resolve()
    pm2_home.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "PM2_HOME": str(pm2_home),
            "PM2_SILENT": "true",
            "PM2_WINDOWS_HIDE": "1",
            "DANMAKU_TTS_SILENT": "1",
        }
    )
    return env


def run_pm2(*arguments: str, timeout: float = 120) -> int:
    command = [str(find_node()), str(find_pm2_script()), *arguments, "--silent"]
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=pm2_environment(),
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            **hidden_process_options(),
        )
    return result.returncode


def read_health(port: int) -> dict | None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
            payload = json.loads(response.read())
    except (OSError, URLError, ValueError):
        return None
    if payload.get("status") not in {"cold", "loading", "ready", "error"}:
        return None
    return payload


def request_endpoint(port: int, route: str, timeout: float = 8) -> dict | None:
    try:
        with urlopen(f"http://127.0.0.1:{port}{route}", timeout=timeout) as response:
            return json.loads(response.read())
    except (OSError, URLError, ValueError):
        return None


def start(port: int) -> int:
    existing = read_health(port)
    if existing:
        log(f"start skipped; supervisor already reports {existing.get('status')}")
        return 0
    code = run_pm2("start", str(ECOSYSTEM), "--only", APP_NAME, "--update-env")
    if code != 0:
        log(f"pm2 start failed with exit code {code}")
        return code
    save_code = run_pm2("save", timeout=30)
    if save_code != 0:
        log(f"pm2 save failed with exit code {save_code}")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        health = read_health(port)
        if health:
            log(f"supervisor started with status={health.get('status')}")
            return 0
        time.sleep(0.5)
    log("supervisor did not answer the health check after pm2 start")
    return 1


def restart(port: int) -> int:
    request_endpoint(port, "/unload", timeout=20)
    code = run_pm2("delete", APP_NAME)
    if code != 0:
        log(f"pm2 delete returned {code}; continuing with a fresh start")
    return start(port)


def stop(port: int) -> int:
    request_endpoint(port, "/unload", timeout=20)
    code = run_pm2("stop", APP_NAME, timeout=30)
    if code != 0:
        log(f"pm2 stop returned {code}")
        return code
    log("supervisor stopped")
    return 0


def warm(port: int) -> int:
    health = read_health(port)
    if not health:
        code = start(port)
        if code != 0:
            return code
    payload = request_endpoint(port, "/warm")
    if payload is None:
        log("warm request failed")
        return 1
    log(f"warm request accepted with status={payload.get('status')}")
    return 0


def status(port: int) -> int:
    health = read_health(port)
    if health is None:
        log("status unavailable")
        return 1
    log(f"status={json.dumps(health, ensure_ascii=False, sort_keys=True)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--action",
        choices=("start", "restart", "stop", "warm", "status"),
        default="start",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise ValueError("invalid port")
    actions = {
        "start": start,
        "restart": restart,
        "stop": stop,
        "warm": warm,
        "status": status,
    }
    try:
        return actions[args.action](args.port)
    except Exception as exc:
        log(f"{args.action} failed: {exc!r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
