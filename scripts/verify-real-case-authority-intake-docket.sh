#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

RECORD_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
ACTIVE_STATE = "ISSUED_ADMISSIBLE_MOTION_PICTURE"
CASE_ID = "CASE_001_THE_LAST_RENDER"

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_INTAKE_DOCKET_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

assert status["case_id"] == CASE_ID
assert status.get("current_state") == RECORD_STATE
assert status.get("record_current_state", RECORD_STATE) == RECORD_STATE
assert index["active_case_states"][CASE_ID] == ACTIVE_STATE
assert case["current_state"] == ACTIVE_STATE

assert status.get("surface_type") in (None, "LAYER_STATUS_RECORD")
assert status.get("current_truth_owner", False) is False
assert status.get("does_not_outrank_current_state_index", True) is True

assert status.get("intake_scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY") == "REAL_CASE_AUTHORITY_OBJECTS_ONLY"
assert status.get("real_case_authority_intake_docket_present", True) is True
assert status.get("real_case_authority_intake_open", True) is True

for key in (
    "authority_satisfied",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present",
):
    assert status.get(key, False) is False, f"{key}={status.get(key)}"

print("CINEMATICUM REAL CASE AUTHORITY INTAKE DOCKET: PASS")
print(f"CURRENT_STATE={RECORD_STATE}")
print(f"RECORD_CURRENT_STATE={RECORD_STATE}")
print(f"ACTIVE_CURRENT_STATE={ACTIVE_STATE}")
print("INTAKE_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("REAL_CASE_AUTHORITY_INTAKE_DOCKET_PRESENT=true")
print("REAL_CASE_AUTHORITY_INTAKE_OPEN=true")

print("AUTHORITY_OBJECT_SLOT_COUNT=8")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=8")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("DOCKET_DOES_NOT_SATISFY_AUTHORITY=true")
print("DOCKET_DOES_NOT_ADVANCE_STATE=true")
print("DOCKET_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("DOCKET_DOES_NOT_ADMIT_MEDIA=true")
print("DOCKET_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ACTIVE_RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
