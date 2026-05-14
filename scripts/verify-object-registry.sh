#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_OBJECT_REGISTRY_LAW.json
test -f CINEMATICUM_SURFACE_CLASS_CATALOG.json
test -f CINEMATICUM_OBJECT_REGISTRY.json
test -f OBJECT_REGISTRY.md

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path(".")
registry_path = root / "CINEMATICUM_OBJECT_REGISTRY.json"
registry = json.loads(registry_path.read_text())

entries = registry.get("entries", [])
by_path = {entry["path"]: entry for entry in entries}

assert registry.get("object_type") == "CINEMATICUM_OBJECT_REGISTRY"
assert registry.get("entries_count") == len(entries)
assert len(by_path) == len(entries), "duplicate registry path"

for entry in entries:
    p = root / entry["path"]
    assert p.exists(), f"missing registry object: {entry['path']}"
    expected = hashlib.sha256(p.read_bytes()).hexdigest()
    assert entry.get("sha256") == expected, f"{entry['path']}: stale sha256"

def load(path):
    return json.loads((root / path).read_text())

def require_file(path, **expected):
    obj = load(path)
    for key, value in expected.items():
        assert obj.get(key) == value, f"{path}: expected {key}={value!r}, got {obj.get(key)!r}"

# Issuance truth surfaces.
for path in (
    "MOTION_PICTURE_ISSUANCE_ACT.json",
    "CASES/CASE_001_THE_LAST_RENDER/MOTION_PICTURE_ISSUANCE_ACT_STATUS.json",
):
    assert path in by_path, f"missing registry entry: {path}"
    require_file(
        path,
        current_state="RELEASE_CANDIDATE_READY",
        issued=True,
        media_present=True,
        issued_object="HASH_BOUND_MOTION_PICTURE_MEDIA",
        next_required_object="NONE",
    )

# Repository/current-state summaries remain non-issuing.
for path in (
    "CINEMATICUM_CURRENT_STATE_INDEX.json",
    "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json",
    "CINEMATICUM_REPOSITORY_STATUS_SEAL.json",
    "CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json",
):
    assert path in by_path, f"missing registry entry: {path}"
    require_file(
        path,
        current_state="RELEASE_CANDIDATE_READY",
        issued=False,
        media_present=False,
        issued_object=None,
    )

print("OBJECT_REGISTRY_OK=true")
print("RELEASE_CANDIDATE_READY=true")
print("CANONICAL_ISSUANCE_BOUNDARY_SPLIT=true")
PY
