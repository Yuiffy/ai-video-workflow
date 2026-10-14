"""Import the reviewed local edit into the existing Dreamina canvas, without generation."""
import hashlib
import json

import produce

assembly = produce.PLAN["assembly"]
film = produce.OUT / assembly.get("output_file", "sui-suddenly-life.mp4")
qa = json.loads((produce.OUT / "media-qa.json").read_text(encoding="utf-8"))
assert qa["full_decode"] == "passed"
assert qa["selected_sources"] == assembly["selected_sources"]
digest = hashlib.sha256(film.read_bytes()).hexdigest()
item_key = "final_" + assembly["revision"] if assembly.get("revision") else "final"
item = produce.job["items"].setdefault(item_key, {**produce.identity(), "type": "video"})
if item.get("sha256") and item["sha256"] != digest:
    raise RuntimeError("The reviewed final file changed; keep the existing canvas import intact")
item.update(sha256=digest, localFile=str(film))
produce.save()
if not item.get("uploaded"):
    result = produce.call("resource", "upload", "--project-id", produce.job["canvasId"],
                          "--resource-id", item["resourceId"], "--file", film,
                          "--type", "video", "--name", "若不是岁己突然闯进我生活·完整成片")
    assert result["resourceId"] == item["resourceId"]
    assert result["mediaType"] == "video"
    item["uploaded"] = True
    produce.save()
if not item.get("saved"):
    result = produce.call("node", "create", "video", "--project-id", produce.job["canvasId"],
                          "--node-id", item["nodeId"], "--update-id", item["updateId"],
                          "--title", assembly.get("canvas_title", "最终成片·岁己版32.6秒"), "--resource-id", item["resourceId"],
                          "--import-kind", "local_upload", "--submit-id", item["submitId"])
    assert result["node"]["type"] == "video"
    item["saved"] = True
    item["selectedResourceId"] = item["resourceId"]
    produce.save()
result = produce.call("node", "show", "--project-id", produce.job["canvasId"], "--node-id", item["nodeId"])
assert any(entry.get("result") == "FOUND" and entry.get("node", {}).get("type") == "video"
           for entry in result["nodes"])
produce.job["delivery"] = {"state": "reviewed", "localFile": str(film), "sha256": digest,
                           "canvasNodeId": item["nodeId"], "selectedSources": qa["selected_sources"],
                           "durationSeconds": 32.6, "published": False}
produce.save()
print(json.dumps(produce.job["delivery"], ensure_ascii=False, indent=2))
