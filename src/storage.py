"""UTF-8 JSON state; writes replace files atomically."""
import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        last_error = None
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                last_error = None
                break
            except PermissionError as error:
                last_error = error
                if attempt == 3:
                    raise
                time.sleep(0.25 * (attempt + 1))
        if last_error is not None:
            raise last_error
    finally:
        temporary.unlink(missing_ok=True)
