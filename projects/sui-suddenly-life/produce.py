"""Prepare, quote and resume this video's documented Dreamina canvas job."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
PLAN = json.loads(Path(__file__).with_name("production-plan.json").read_text(encoding="utf-8"))
OUT = ROOT / PLAN["output"]
STATE = OUT / "job.json"
EXE = "C:/Users/yuiffy/bin/dreamina-canvas.exe"
OUT.mkdir(parents=True, exist_ok=True)
job = json.loads(STATE.read_text(encoding="utf-8"))
SCENES = PLAN["scenes"] + PLAN.get("repairs", [])


def selected_scenes():
    if args.keys:
        result = [scene for scene in SCENES if scene["id"] in args.keys]
        assert {scene["id"] for scene in result} == set(args.keys)
        return result
    return PLAN["scenes"]


def save():
    temporary = STATE.with_name(f"job-{os.getpid()}.tmp")
    temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(8):
        try:
            os.replace(temporary, STATE)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.2 * (attempt + 1))


def identity():
    return {
        "nodeId": "node_" + "".join(secrets.choice("0123456789abcdefghjkmnpqrstvwxyz") for _ in range(10)),
        "resourceId": str(uuid.uuid4()),
        "updateId": str(uuid.uuid4()),
        "submitId": str(uuid.uuid4()),
    }


def call(*args):
    result = subprocess.run(
        [EXE, "--non-interactive", "--profile", job["profile"], "--region", job["region"], *map(str, args)],
        capture_output=True, encoding="utf-8", errors="replace", timeout=120,
    )
    envelope = json.loads(result.stdout or result.stderr)
    request_id = envelope.get("meta", {}).get("requestId")
    if request_id:
        job["requestIds"].append({"command": " ".join(map(str, args[:2])), "requestId": request_id})
        save()
    if not envelope.get("ok"):
        job["lastError"] = {key: envelope[key] for key in ("error", "partialData", "creditConfirmation", "meta") if key in envelope}
        save()
        raise RuntimeError(json.dumps(job["lastError"], ensure_ascii=False))
    return envelope["data"]


def prepare():
    for key, ref in PLAN["references"].items():
        item = job["items"].setdefault(key, {**identity(), "type": ref["type"]})
        save()
        if not item.get("uploaded"):
            uploaded = call("resource", "upload", "--project-id", job["canvasId"], "--resource-id", item["resourceId"],
                            "--file", ref["file"], "--type", ref["type"], "--name", ref["title"])
            assert uploaded["resourceId"] == item["resourceId"]
            assert uploaded["mediaType"] == ref["type"]
            item["uploaded"] = True
            save()
        if not item.get("saved"):
            data = call("node", "create", ref["type"], "--project-id", job["canvasId"], "--node-id", item["nodeId"],
                        "--update-id", item["updateId"], "--title", ref["title"], "--resource-id", item["resourceId"],
                        "--import-kind", "local_upload", "--submit-id", item["submitId"])
            assert data["node"]["type"] == ref["type"]
            item["saved"] = True
            save()
        print(key + " imported", flush=True)
    for scene in selected_scenes():
        key = scene["id"]
        media_type = scene.get("type", "video")
        item = job["items"].setdefault(key, {**identity(), "type": media_type})
        save()
        prompt = scene["prompt"]
        for ref in scene["refs"]:
            prompt = prompt.replace("{{" + ref + "}}", "{{node:" + job["items"][ref]["nodeId"] + "}}")
        previous = item.get("generation", {})
        if item.get("saved") and previous.get("prompt") == prompt and previous.get("model") == scene["model"] and previous.get("durationSeconds") == scene.get("duration"):
            continue
        verb = "create"
        if item.get("saved"):
            if item.get("attempted"):
                raise RuntimeError("Cannot change an already attempted generation")
            current = call("node", "show", "--project-id", job["canvasId"], "--node-id", item["nodeId"])
            assert any(entry.get("result") == "FOUND" and entry.get("node", {}).get("nodeId") == item["nodeId"] for entry in current.get("nodes", []))
            item["updateId"] = str(uuid.uuid4())
            save()
            verb = "edit"
        args = ["node", verb, media_type, "--project-id", job["canvasId"], "--node-id", item["nodeId"],
                "--update-id", item["updateId"], "--title", scene["title"],
                "--mode", scene.get("mode", "m2v" if media_type == "video" else "i2i"), "--model", scene["model"],
                "--ratio", "16:9", "--resolution", scene.get("resolution", "720p"), "--count", "1", "--prompt", prompt]
        if media_type == "video":
            args += ["--duration", scene["duration"]]
        for ref in scene["refs"]:
            args += ["--ref", "node:" + job["items"][ref]["nodeId"]]
        node = call(*args)["node"]
        expected = {job["items"][ref]["nodeId"] for ref in scene["refs"]}
        assert expected.issubset(set(node["upstreamNodeIds"]))
        references = node["generation"]["references"]
        assert expected == {ref["id"] for ref in references if ref["kind"] == "node"}
        assert node["generation"]["prompt"] == prompt
        item.update(saved=True, generation=node["generation"], upstreamNodeIds=node["upstreamNodeIds"])
        save()
        print(key + " saved", flush=True)


def node_args():
    args = ["--project-id", job["canvasId"]]
    for scene in selected_scenes():
        args += ["--node-id", job["items"][scene["id"]]["nodeId"]]
    return args


def quote():
    data = call("node", "quote", *node_args())
    job["lastQuote"] = data
    save()
    print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)
    return data


def run(ceiling):
    items = [job["items"][scene["id"]] for scene in selected_scenes()]
    if any(item.get("attempted") for item in items):
        raise RuntimeError("Submission already attempted; resume with status rather than paying again")
    quoted = quote()
    if not quoted.get("confirmable", True):
        raise RuntimeError("Quote incomplete; generation was not submitted")
    if quoted.get("confirmationRequired") and ceiling is None:
        raise RuntimeError("Explicit user credit ceiling approval required")
    if ceiling is not None and quoted["totalMaxCredits"] > ceiling:
        raise RuntimeError("Latest quote exceeds approved ceiling")
    reserved = sum(item.get("quotedMaxCredits", 0) for item in job["items"].values() if item.get("attempted"))
    if reserved + quoted["totalMaxCredits"] > job["budget"]["authorizedTotalCeiling"]:
        raise RuntimeError("This batch would exceed the user's total budget")
    token = None
    if quoted.get("confirmationRequired"):
        token = call("node", "confirm", *node_args(), "--credit-ceiling", ceiling)["creditConfirmationToken"]
    args = ["node", "run", *node_args()]
    costs = {item["nodeId"]: item["maxCredits"] for item in quoted["items"]}
    for item in items:
        item.update(attempted=True, authorizedCreditCeiling=ceiling, quotedMaxCredits=costs[item["nodeId"]])
        args += ["--submit-id", item["submitId"]]
    job["budget"]["nominalReservedCredits"] = reserved + quoted["totalMaxCredits"]
    job["budget"]["remainingCeiling"] = job["budget"]["authorizedTotalCeiling"] - job["budget"]["nominalReservedCredits"]
    save()
    if token:
        args += ["--credit-token", token]
    data = call(*args)
    for result in data["items"]:
        next(item for item in items if item["nodeId"] == result["nodeId"])["runResult"] = result
    save()
    print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)


def status():
    for scene in selected_scenes():
        item = job["items"][scene["id"]]
        if not item.get("attempted"):
            continue
        data = call("operation", "status", item["submitId"], "--project-id", job["canvasId"])
        item["observation"] = data
        save()
        print(json.dumps({"scene": scene["id"], **data}, ensure_ascii=False), flush=True)


def download():
    for scene in selected_scenes():
        item = job["items"][scene["id"]]
        resources = [r for r in item.get("observation", {}).get("resources", []) if r.get("state", "").lower() in ("success", "succeeded")]
        if not resources:
            print(scene["id"] + " not ready", flush=True)
            continue
        item["selectedResourceId"] = resources[0]["resourceId"]
        save()
        image_format = resources[0].get("format", "png").lower()
        image_suffix = ".jpg" if image_format in ("jpeg", "jpg") else ".png"
        suffix = "-raw.mp4" if item["type"] == "video" else image_suffix
        target = OUT / (scene["id"] + suffix)
        if not target.exists():
            item["download"] = call("resource", "download", item["selectedResourceId"], "--project-id", job["canvasId"], "--output", target)
        assert target.stat().st_size > 1000
        item["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        item["localFile"] = str(target)
        if item.get("download", {}).get("sha256"):
            assert item["download"]["sha256"].lower() == item["sha256"]
        save()
        print(scene["id"] + " downloaded", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "quote", "run", "status", "download"])
    parser.add_argument("keys", nargs="*")
    parser.add_argument("--ceiling", type=int)
    args = parser.parse_args()
    if args.action == "run":
        run(args.ceiling)
    else:
        globals()[args.action]()
