from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path


class JimengCli:
    def __init__(self, command: list[str], model: str, ratio: str, duration: int, video_resolution: str = "720p", executable: str | None = None, images: list[str] | None = None, poll: int = 0):
        self.command, self.model, self.ratio, self.duration = command, model, ratio, duration
        self.video_resolution, self.executable, self.images, self.poll = video_resolution, executable, images or [], poll

    def plan(self, prompt: str, output_dir: Path, scene_id: str) -> dict:
        values = {"model": self.model, "prompt": prompt, "ratio": self.ratio, "duration": str(self.duration), "video_resolution": self.video_resolution}
        command: list[str] = []
        for part in self.command:
            if part == "{images}":
                for image in self.images:
                    command.extend(["--image", image])
            else:
                command.append(part.format(**values))
        if self.executable:
            command.insert(0, self.executable)
        return {"scene_id": scene_id, "command": command, "shell": shlex.join(command), "output_dir": str(output_dir), "images": self.images}

    def run(self, prompt: str, output_dir: Path, scene_id: str) -> dict:
        plan = self.plan(prompt, output_dir, scene_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(plan["command"], cwd=output_dir, text=True, capture_output=True)
        plan.update({"returncode": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]})
        match = re.search(r"(?:submit_id|submitId)[^A-Za-z0-9]+([A-Za-z0-9_-]{8,})", result.stdout + result.stderr)
        if match:
            plan["submit_id"] = match.group(1)
            query = [self.executable or "dreamina", "query_result", "--submit_id", match.group(1), "--download_dir", str(output_dir)]
            query_result = subprocess.run(query, cwd=output_dir, text=True, capture_output=True, timeout=max(self.duration * 30, 300))
            plan.update({"query_returncode": query_result.returncode, "query_stdout": query_result.stdout[-4000:], "query_stderr": query_result.stderr[-4000:]})
            if query_result.returncode:
                raise RuntimeError(f"即梦查询/下载失败 ({query_result.returncode}): {query_result.stderr[-500:]}")
        if result.returncode:
            raise RuntimeError(f"即梦命令失败 ({result.returncode}): {result.stderr[-500:]}")
        return plan
