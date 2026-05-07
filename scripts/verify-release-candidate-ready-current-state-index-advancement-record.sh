#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE = "CASE_001_THE_LAST_RENDER"
FROM_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
TO_STATE = "RELEASE_CANDIDATE_READY"
OBJECT = "RELEASE_CANDIDATE_READY_CURRENT_STATE_INDEX_ADVANCEMENT_RECORD"
RECORD_ID = "ADV_001_RELEASE_CANDIDATE_READY_CURRENT_STATE_INDEX_ADVANCEMENT"

record_path = Path("CASES") / CASE / OBJECT / f"{RECORD_ID}.json"
status_path = Path("CASES") / CASE / f"{OBJECT}_STATUS.json"
root_path = Path("CINEMATICUM_RELEASE_CANDIDATE_READY_CURRENT_STATE_INDEX_ADVANCEMENT_RECORD.json")
law_path = Path("CINEMATICUM_RELEASE_CANDIDATE_READY_CURRENT_STATE_INDEX_ADVANCEMENT_RECORD_LAW.json")

for path in [record_path, status_path, root_path, law_path]:
    if not path.exists():
        raise SystemExit(f"missing required file: {path}")

record = json.loads(record_path.read_text())
status = json.loads(status_path.read_text())
root = json.loads(root_path.read_text())
law = json.loads(law_path.read_text())

assert record == root
assert record["object"] == OBJECT
assert record["record_id"] == RECORD_ID
assert record["from_state"] == FROM_STATE
assert record["to_state"] == TO_STATE
assert record["prior_execution_object"] == "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_EXECUTION_RECORD"
assert record["prior_execution_id"] == "EXEC_001_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT"
assert record["state_mutation_execution_authorized"] is True
assert record["current_state_index_mutation_authorized"] is True
assert record["current_state_index_mutation_executed"] is True
assert record["current_state_index_now_points_to_to_state"] is True
assert record["authority_satisfied_for_transition"] is True
assert record["release_candidate_ready"] is True
assert record["issued"] is False
assert record["media_present"] is False
assert status["present"] is True
assert status["sealed"] is True
assert law["governs_object"] == OBJECT
assert law["authorizes_current_state_index_mutation_to_release_candidate_ready"] is True

def find_active_state(obj):
    if isinstance(obj, dict):
        for key in ("active_current_state", "ACTIVE_CURRENT_STATE", "current_state", "CURRENT_STATE"):
            if key in obj and obj[key] in {FROM_STATE, TO_STATE}:
                return obj[key]
        for value in obj.values():
            found = find_active_state(value)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_active_state(value)
            if found:
                return found
    return None

index_candidates = [
    Path("CINEMATICUM_CURRENT_STATE_INDEX.json"),
    Path("CURRENT_STATE_INDEX.json"),
    Path("CASES") / CASE / "CURRENT_STATE_INDEX.json",
]

active = None
for path in index_candidates:
    if path.exists():
        active = find_active_state(json.loads(path.read_text()))
        if active:
            break

if active is None:
    for path in Path(".").rglob("*CURRENT_STATE_INDEX*.json"):
        if "ADVANCEMENT_RECORD" in path.name:
            continue
        try:
            active = find_active_state(json.loads(path.read_text()))
        except Exception:
            continue
        if active:
            break

assert active == TO_STATE, f"current state index not advanced: {active!r}"

print("CINEMATICUM RELEASE CANDIDATE READY CURRENT STATE INDEX ADVANCEMENT RECORD: PASS")
print(f"FROM_STATE={FROM_STATE}")
print(f"TO_STATE={TO_STATE}")
print("PRIOR_EXECUTION_OBJECT=RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_EXECUTION_RECORD")
print("STATE_MUTATION_EXECUTION_AUTHORIZED=true")
print("CURRENT_STATE_INDEX_MUTATION_AUTHORIZED=true")
print("CURRENT_STATE_INDEX_MUTATION_EXECUTED=true")
print("CURRENT_STATE_INDEX_NOW_POINTS_TO_TO_STATE=true")
print("RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("NEXT_REQUIRED_OBJECT=RELEASE_CANDIDATE_READY_REPOSITORY_STATUS_SEAL")
PY
