#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_CURRENT_STATE_INDEX.json
test -f CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
TARGET = "RELEASE_CANDIDATE_READY"

index = json.loads(Path("CINEMATICUM_CURRENT_STATE_INDEX.json").read_text())
case = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json").read_text())

def require(cond, msg):
    if not cond:
        raise AssertionError(msg)

def walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk_dicts(value)

require(index.get("current_state") == TARGET, f"index.current_state={index.get('current_state')!r}")
require(index.get("active_case_states", {}).get(CASE_ID) == TARGET, f"active_case_states[{CASE_ID}]={index.get('active_case_states', {}).get(CASE_ID)!r}")
require(case.get("current_state") == TARGET, f"case.current_state={case.get('current_state')!r}")

# Validate any nested case entry that exists, without requiring a specific schema key like index["cases"].
nested_case_entries = [
    obj for obj in walk_dicts(index)
    if obj.get("case_id") == CASE_ID or obj.get("id") == CASE_ID
]

for entry in nested_case_entries:
    if "current_state" in entry:
        require(entry["current_state"] == TARGET, f"nested.current_state={entry['current_state']!r}")
    if "issued" in entry:
        require(entry["issued"] is False, f"nested.issued={entry['issued']!r}")
    if "media_present" in entry:
        require(entry["media_present"] is False, f"nested.media_present={entry['media_present']!r}")
    if "issued_object" in entry:
        require(entry["issued_object"] is None, f"nested.issued_object={entry['issued_object']!r}")

for label, obj in (("index", index), ("case", case)):
    require(obj.get("release_candidate_ready") is True, f"{label}.release_candidate_ready={obj.get('release_candidate_ready')!r}")
    require(obj.get("issued") is False, f"{label}.issued={obj.get('issued')!r}")
    require(obj.get("media_present") is False, f"{label}.media_present={obj.get('media_present')!r}")
    require(obj.get("issued_object") is None, f"{label}.issued_object={obj.get('issued_object')!r}")

print("CINEMATICUM CURRENT STATE INDEX: PASS")
print(f"CASE_ID={CASE_ID}")
print(f"CURRENT_STATE={TARGET}")
print("RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("ISSUED_OBJECT=None")
PY
