"""Official Dreamina CLI with durable, resumable submissions."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from filelock import FileLock

from .storage import digest, file_digest, read_json, write_json


class JimengCli:
    def __init__(self, config: dict):
        self.config = config
        self.exe = config.get("executable", "dreamina")

    def plan(self, prompt: str, output_dir: Path, scene_id: str,
             duration: int | None = None, audio: str | None = None) -> dict:
        model = self.config.get("model", "seedance2.0fast_vip")
        duration = duration or self.config.get("duration", 10)
        if model not in {"seedance2.0fast_vip", "seedance2.0mini"}:
            raise ValueError("This adapter currently supports seedance2.0fast_vip and seedance2.0mini")
        if not 4 <= duration <= 15:
            raise ValueError("Dreamina shots must be 4–15 seconds; narration may be longer")
        images = self.config.get("images", [])
        audios = [audio] if audio else self.config.get("audio_references", [])
        if audios and not images:
            raise ValueError("These models require an image alongside an audio reference")
        if len(images) > 9 or len(audios) > 3 or len(images) + len(audios) > 12:
            raise ValueError("Too many Dreamina reference inputs")
        resolution = self.config.get("video_resolution", "720p")
        if resolution != "720p":
            raise ValueError("The installed CLI supports 720p for these two models")
        command = [self.exe, "multimodal2video" if images else "text2video"]
        for image in images:
            command += ["--image", str(image)]
        for reference in audios:
            command += ["--audio", str(reference)]
        command += ["--model_version", model, "--prompt", prompt, "--ratio",
                    self.config.get("ratio", "16:9"), "--duration", str(duration),
                    "--video_resolution", resolution, "--poll", "0"]
        return {"scene_id": scene_id, "command": command, "prompt": prompt,
                "output_dir": str(output_dir.resolve()), "images": images, "audios": audios}

    def _call(self, args: list[str], output_dir: Path, response_file: str) -> dict:
        result = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace",
                                timeout=self.config.get("timeout_seconds", 240))
        write_json(output_dir / response_file, {"returncode": result.returncode,
                   "stdout": result.stdout, "stderr": result.stderr})
        # A submit ID can still be present in a nonzero response; preserve it before
        # considering retries. No path in this class retries a paid submission.
        try:
            payload = json.loads(result.stdout)
        except ValueError as exc:
            raise RuntimeError(f"Dreamina returned no JSON; inspect {response_file}") from exc
        if result.returncode and not payload.get("submit_id"):
            raise RuntimeError(f"Dreamina command failed; inspect {response_file}")
        return payload

    def query(self, output_dir: Path) -> dict:
        output_dir = output_dir.resolve()
        with FileLock(str(output_dir / "job.lock"), timeout=0):
            job = read_json(output_dir / "job.json")
            if not job.get("submit_id"):
                raise RuntimeError("Submission outcome is unknown. Recover its ID; do not resubmit")
            data = self._call([self.exe, "query_result", "--submit_id", job["submit_id"],
                               "--download_dir", str(output_dir)], output_dir, "query-response.json")
            if data.get("submit_id") != job["submit_id"]:
                raise RuntimeError("Dreamina returned a different submit ID")
            job.update(gen_status=data.get("gen_status", "unknown"),
                       result_json=data.get("result_json", {}), fail_reason=data.get("fail_reason", ""))
            job["prompt"] = data.get("prompt")
            videos = []
            for item in job["result_json"].get("videos", []):
                path = Path(item.get("path", ""))
                if path.is_file() and path.stat().st_size > 0:
                    videos.append(str(path.resolve()))
            job["videos"] = videos
            job["downloaded"] = job["gen_status"] == "success" and bool(videos)
            write_json(output_dir / "job.json", job)
            return job

    def run(self, prompt: str, output_dir: Path, scene_id: str,
            duration: int | None = None, audio: str | None = None) -> dict:
        plan = self.plan(prompt, output_dir, scene_id, duration, audio)
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        references = plan["images"] + plan["audios"]
        for ref in references:
            if not Path(ref).is_file():
                raise FileNotFoundError(ref)
        fingerprint = digest({"command": plan["command"],
                              "references": [file_digest(Path(ref)) for ref in references]})
        job_path = output_dir / "job.json"
        with FileLock(str(output_dir / "job.lock"), timeout=0):
            if job_path.exists():
                old = read_json(job_path)
                if old.get("fingerprint") != fingerprint:
                    raise RuntimeError("An existing job uses another request. Poll or explicitly adopt it")
                if not old.get("submit_id"):
                    raise RuntimeError("Submission outcome is unknown; recover the ID before continuing")
            else:
                # Persist intent first so a killed process cannot silently submit again.
                job = {**plan, "fingerprint": fingerprint, "gen_status": "submitting"}
                write_json(job_path, job)
                data = self._call(plan["command"], output_dir, "submit-response.json")
                job.update(submit_id=data.get("submit_id"), gen_status=data.get("gen_status", "unknown"),
                           credit_count=data.get("credit_count"))
                write_json(job_path, job)
                if not job["submit_id"]:
                    raise RuntimeError("No submit ID returned. Inspect saved response; do not resubmit")
        return self.query(output_dir)

    def adopt(self, output_dir: Path, submit_id: str, prompt: str, scene_id: str) -> dict:
        """Recover a known task without a paid submission."""
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        with FileLock(str(output_dir / "job.lock"), timeout=0):
            data = self._call([self.exe, "query_result", "--submit_id", submit_id,
                               "--download_dir", str(output_dir)], output_dir, "query-response.json")
            if data.get("submit_id") != submit_id or data.get("prompt") != prompt:
                raise ValueError("Recovered task does not match this scene")
            write_json(output_dir / "job.json", {"scene_id": scene_id, "submit_id": submit_id,
                       "prompt": prompt, "gen_status": data.get("gen_status"), "recovered": True})
        return self.query(output_dir)
