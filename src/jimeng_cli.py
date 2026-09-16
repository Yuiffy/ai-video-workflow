from __future__ import annotations

import shlex
import subprocess
from pathlib import Path


class JimengCli:
    def __init__(self, command: list[str], model: str, ratio: str, duration: int):
        self.command, self.model, self.ratio, self.duration = command, model, ratio, duration

    def plan(self, prompt: str, output_dir: Path, scene_id: str) -> dict:
        values = {"model": self.model, "prompt": prompt, "ratio": self.ratio, "duration": str(self.duration)}
        command = [part.format(**values) for part in self.command]
        return {"scene_id": scene_id, "command": command, "shell": shlex.join(command), "output_dir": str(output_dir)}

    def run(self, prompt: str, output_dir: Path, scene_id: str) -> dict:
        plan = self.plan(prompt, output_dir, scene_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(plan["command"], cwd=output_dir, text=True, capture_output=True)
        plan.update({"returncode": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]})
        if result.returncode:
            raise RuntimeError(f"即梦命令失败 ({result.returncode}): {result.stderr[-500:]}")
        return plan
