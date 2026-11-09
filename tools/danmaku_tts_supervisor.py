"""Keep the danmaku TTS endpoint alive while loading RVC only on demand."""
from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.json"
WORKER_SCRIPT = ROOT / "tools/rvc_danmaku_server.py"
DEFAULT_CACHE = ROOT / "outputs/danmaku-tts/cache"
DEFAULT_HOST_PROCESS = "Bililive_dm.exe"


def hidden_process_options() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
        "close_fds": True,
    }


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def host_process_running(process_name: str) -> bool:
    """Check the danmaku host process without spawning tasklist.exe."""
    if os.name != "nt" or not process_name:
        return False

    import ctypes
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if not snapshot or snapshot == invalid_handle:
        return False

    wanted = process_name.casefold()
    entry = ProcessEntry32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        available = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            if entry.szExeFile.casefold() == wanted:
                return True
            available = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return False


def worker_request(port: int, path: str, timeout: float = 5) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


class WorkerManager:
    def __init__(self, config_path: Path, cache_dir: Path, idle_seconds: int):
        self.config_path = config_path.resolve()
        self.cache_dir = cache_dir.resolve()
        self.idle_seconds = max(30, idle_seconds)
        self.start_timeout = 300
        self.state_lock = threading.RLock()
        self.start_lock = threading.Lock()
        self.request_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.ready_event = threading.Event()
        self.host_process = os.environ.get(
            "DANMAKU_TTS_HOST_PROCESS",
            DEFAULT_HOST_PROCESS,
        )
        self.auto_warm = os.environ.get("DANMAKU_TTS_AUTO_WARM", "1") != "0"
        self.host_was_running = False
        self.manual_unload = False
        self.process: subprocess.Popen | None = None
        self.worker_port: int | None = None
        self.ready = False
        self.error: str | None = None
        self.last_used = time.monotonic()
        self.started_at: float | None = None
        self.last_unloaded_at: float | None = None
        self.unload_reason = ""

        config = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        runtime = Path(config["rvc"]["runtime_python"]).resolve()
        pythonw = runtime.with_name("pythonw.exe")
        self.runtime = pythonw if os.name == "nt" and pythonw.is_file() else runtime
        self.model_name = os.environ.get(
            "DANMAKU_RVC_MODEL",
            str(config["rvc"].get("model", "")),
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.host_was_running = self._host_is_running()
        self.monitor = threading.Thread(
            target=self._monitor_lifecycle,
            name="danmaku-tts-lifecycle-monitor",
            daemon=True,
        )
        self.monitor.start()
        if self.host_was_running:
            threading.Thread(
                target=self._auto_warm,
                name="danmaku-tts-auto-warm",
                daemon=True,
            ).start()

    def _host_is_running(self) -> bool:
        return self.auto_warm and host_process_running(self.host_process)

    def _auto_warm(self) -> None:
        try:
            self.warm(wait=False)
        except Exception as exc:
            print(f"automatic warm failed: {exc}", file=sys.stderr, flush=True)

    def snapshot(self) -> dict:
        host_running = self._host_is_running()
        with self.state_lock:
            self._reap_failed_process()
            if self.state == "cold":
                idle_remaining = 0
            elif self.last_used:
                idle_remaining = max(
                    0,
                    round(self.idle_seconds - (time.monotonic() - self.last_used)),
                )
            else:
                idle_remaining = self.idle_seconds
            payload = {
                "status": self.state,
                "mode": "lazy-worker",
                "model": Path(self.model_name).name,
                "worker_pid": self.process.pid if self.process else None,
                "worker_port": self.worker_port,
                "idle_unload_seconds": self.idle_seconds,
                "idle_remaining_seconds": idle_remaining,
                "last_unload_reason": self.unload_reason,
                "auto_warm": self.auto_warm,
                "host_process": self.host_process,
                "host_process_running": host_running,
                "manual_unload": self.manual_unload,
            }
            if self.error:
                payload["error"] = self.error
            return payload

    @property
    def state(self) -> str:
        if self.error:
            return "error"
        if self.process is None:
            return "cold"
        return "ready" if self.ready else "loading"

    def _reap_failed_process(self) -> None:
        if self.process is None or self.process.poll() is None:
            return
        code = self.process.returncode
        self.process = None
        self.worker_port = None
        self.ready = False
        self.ready_event.set()
        self.error = f"worker exited unexpectedly with code {code}"
        self.unload_reason = "worker-failed"

    def _spawn_worker(self) -> None:
        port = free_loopback_port()
        log_path = self.cache_dir.parent / "worker.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.runtime),
            str(WORKER_SCRIPT),
            "--config",
            str(self.config_path),
            "--cache",
            str(self.cache_dir),
            "--port",
            str(port),
            "--parent-pid",
            str(os.getpid()),
        ]
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
        with log_path.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                **hidden_process_options(),
            )
        with self.state_lock:
            self.process = process
            self.worker_port = port
            self.ready = False
            self.ready_event.clear()
            self.error = None
            self.started_at = time.monotonic()
            self.last_used = time.monotonic()
        print(
            f"starting RVC worker pid={process.pid} port={port}",
            flush=True,
        )
        threading.Thread(
            target=self._watch_startup,
            name="danmaku-tts-worker-ready",
            daemon=True,
        ).start()

    def _watch_startup(self) -> None:
        with self.state_lock:
            process = self.process
        try:
            self._wait_until_ready()
        except Exception as exc:
            with self.state_lock:
                if self.process is process:
                    self.error = str(exc)
            self.ready_event.set()

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self.start_timeout
        while time.monotonic() < deadline:
            with self.state_lock:
                process = self.process
                port = self.worker_port
                if process is None or port is None:
                    raise RuntimeError(self.error or "RVC worker failed to start")
                if process.poll() is not None:
                    self._reap_failed_process()
                    raise RuntimeError(self.error or "RVC worker exited during startup")
            try:
                status, body = worker_request(port, "/health", timeout=2)
                payload = json.loads(body)
                if status == 200 and payload.get("status") == "ready":
                    with self.state_lock:
                        self.ready = True
                        self.last_used = time.monotonic()
                        self.ready_event.set()
                    print(
                        f"RVC worker ready in {time.monotonic() - (self.started_at or time.monotonic()):.1f}s",
                        flush=True,
                    )
                    return
                if payload.get("status") == "error":
                    raise RuntimeError(payload.get("error") or "RVC worker failed")
            except (OSError, ValueError, http.client.HTTPException):
                pass
            time.sleep(0.5)
        raise TimeoutError(f"RVC worker did not become ready within {self.start_timeout}s")

    def warm(self, wait: bool = False) -> dict:
        with self.state_lock:
            self.manual_unload = False
        with self.start_lock:
            with self.state_lock:
                self._reap_failed_process()
                alive = self.process is not None and self.process.poll() is None
            if not alive:
                self._spawn_worker()
        if wait:
            self.ready_event.wait(timeout=self.start_timeout + 1)
            with self.state_lock:
                if self.error:
                    raise RuntimeError(self.error)
                if not self.ready:
                    raise TimeoutError(
                        f"RVC worker did not become ready within {self.start_timeout}s"
                    )
        return self.snapshot()

    def _proxy_tts(self, query: str) -> tuple[str, bytes]:
        self.warm(wait=True)
        with self.state_lock:
            port = self.worker_port
        if port is None:
            raise RuntimeError("RVC worker port is unavailable")
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=180)
        try:
            connection.request("GET", "/tts?" + query)
            response = connection.getresponse()
            content_type = response.getheader("Content-Type", "application/json; charset=utf-8")
            data = response.read()
        finally:
            connection.close()
        if response.status == 200:
            with self.state_lock:
                self.last_used = time.monotonic()
        return content_type, data

    def speak(self, query: str) -> tuple[str, bytes]:
        with self.request_lock:
            return self._proxy_tts(query)

    def unload(self, reason: str = "manual") -> dict:
        with self.request_lock:
            with self.state_lock:
                process = self.process
                self.ready = False
                self.ready_event.clear()
                self.error = None
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            with self.state_lock:
                was_loaded = process is not None
                self.process = None
                self.worker_port = None
                self.ready = False
                self.ready_event.clear()
                self.error = None
                self.unload_reason = reason
                self.manual_unload = reason == "manual"
                if was_loaded:
                    self.last_unloaded_at = time.monotonic()
            if process is not None:
                print(f"RVC worker unloaded reason={reason}", flush=True)
            return self.snapshot()

    def _monitor_lifecycle(self) -> None:
        while not self.stop_event.wait(2):
            host_running = self._host_is_running()
            if host_running and not self.host_was_running:
                self.host_was_running = True
                if not self.manual_unload:
                    self._auto_warm()
            elif not host_running and self.host_was_running:
                self.host_was_running = False
                self.manual_unload = False
                if self.process is not None:
                    try:
                        self.unload("host-exited")
                    except Exception as exc:
                        print(f"host-exit unload failed: {exc}", file=sys.stderr, flush=True)
            with self.state_lock:
                should_unload = (
                    self.ready
                    and self.process is not None
                    and not host_running
                    and time.monotonic() - self.last_used >= self.idle_seconds
                )
            if should_unload:
                try:
                    self.unload("idle")
                except Exception as exc:
                    print(f"idle unload failed: {exc}", file=sys.stderr, flush=True)

    def close(self) -> None:
        self.stop_event.set()
        self.unload("shutdown")


class SupervisorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, manager: WorkerManager):
        self.manager = manager
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server: SupervisorServer
    server_version = "DanmakuTTS/2.0"

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
            payload = self.server.manager.snapshot()
            status = 503 if payload["status"] == "error" else 200
            self.reply_json(status, payload)
            return
        if parsed.path == "/warm":
            try:
                self.reply_json(202, self.server.manager.warm(wait=False))
            except Exception as exc:
                self.reply_json(500, {"status": "error", "error": str(exc)})
            return
        if parsed.path == "/unload":
            try:
                self.reply_json(200, self.server.manager.unload())
            except Exception as exc:
                self.reply_json(500, {"status": "error", "error": str(exc)})
            return
        if parsed.path != "/tts":
            self.reply_json(404, {"error": "not found"})
            return
        try:
            content_type, data = self.server.manager.speak(parsed.query)
        except Exception as exc:
            self.reply_json(503, {"error": str(exc)})
            return
        self.reply(200, content_type, data)

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
    parser.add_argument(
        "--idle-seconds",
        type=int,
        default=int(os.environ.get("DANMAKU_TTS_IDLE_UNLOAD_SECONDS", "300")),
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise ValueError("invalid port")
    manager = WorkerManager(args.config, args.cache, args.idle_seconds)
    server = SupervisorServer(("127.0.0.1", args.port), manager)
    warm_mode = (
        f"auto-warm while {manager.host_process} is running"
        if manager.auto_warm
        else "model cold until first request"
    )
    print(
        f"Danmaku TTS supervisor listening on http://127.0.0.1:{args.port}/tts; "
        f"{warm_mode}; idle unload={manager.idle_seconds}s",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        manager.close()


if __name__ == "__main__":
    main()
