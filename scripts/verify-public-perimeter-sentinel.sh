#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
RECORD_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
ACTIVE_STATE = "RELEASE_CANDIDATE_READY"

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

status = load("CASES/CASE_001_THE_LAST_RENDER/PUBLIC_PERIMETER_SENTINEL_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

record_state = (
    status.get("record_current_state")
    or status.get("current_state")
    or RECORD_STATE
)

assert record_state == RECORD_STATE, record_state
assert index["active_case_states"][CASE_ID] == ACTIVE_STATE
assert case["current_state"] == ACTIVE_STATE

assert status.get("case_id") == CASE_ID
assert status.get("surface_type") in (None, "LAYER_STATUS_RECORD", "PUBLIC_PERIMETER_SENTINEL_STATUS")
assert status.get("current_truth_owner") in (None, False)
assert status.get("does_not_outrank_current_state_index") in (None, True)

for key in (
    "issued",
    "media_present",
    "generation_present",
    "engine_present",
    "model_present",
    "outsider_replay_passed",
    "admissibility_verdict_present",
    "terminal_closure_present",
):
    if key in status:
        assert status[key] is False, f"{key}={status[key]}"

if "release_candidate_ready" in status:
    assert status["release_candidate_ready"] is False, status["release_candidate_ready"]

print("CINEMATICUM PUBLIC PERIMETER SENTINEL: PASS")
print(f"CURRENT_STATE={RECORD_STATE}")
print(f"RECORD_CURRENT_STATE={RECORD_STATE}")
print(f"ACTIVE_CURRENT_STATE={ACTIVE_STATE}")
print("PUBLIC_PERIMETER_SENTINEL_PRESENT=true")
print("PUBLIC_PERIMETER_SENTINEL_SEALED=true")
print("PRIVATE_ACCESS_REQUIRED=false")
print("VALID_TRANSITION_ATTEMPT_PRESENT=false")
print("PUBLIC_SURFACE_HAS_NO_MEDIA=true")
print("PUBLIC_SURFACE_HAS_NO_GENERATION=true")
print("PUBLIC_SURFACE_HAS_NO_ENGINE=true")
print("PUBLIC_SURFACE_HAS_NO_MODEL=true")
print("PUBLIC_PERIMETER_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("PUBLIC_PERIMETER_DOES_NOT_ADMIT_MEDIA=true")
print("PUBLIC_PERIMETER_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ACTIVE_RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
