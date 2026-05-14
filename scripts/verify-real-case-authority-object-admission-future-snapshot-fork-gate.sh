#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
RECORD_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
ACTIVE_STATE = "RELEASE_CANDIDATE_READY"

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

gate = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_SNAPSHOT_FORK_GATE.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_SNAPSHOT_FORK_GATE_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

for obj in (gate, status):
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == RECORD_STATE
    assert obj["fork_scope"] == "FUTURE_VALID_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS_CREATE_NEW_SNAPSHOT_ONLY"
    assert obj["future_continuity_seal_present"] is True
    assert obj["permanence_seal_present"] is True
    assert obj["current_zero_admission_snapshot_permanent"] is True
    assert obj["current_zero_admission_snapshot_mutable"] is False
    assert obj["current_zero_admission_snapshot_reopenable_by_future_request"] is False
    assert obj["future_valid_admission_requests_create_new_snapshot"] is True
    assert obj["future_valid_admission_requests_fork_from_current_zero_snapshot"] is True
    assert obj["future_valid_admission_requests_do_not_mutate_current_zero_snapshot"] is True
    assert obj["future_valid_admission_requests_do_not_mutate_terminal_snapshot"] is True
    assert obj["future_snapshot_fork_gate_passed"] is False
    assert obj["future_snapshot_fork_gate_open_now"] is False
    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False

assert index["active_case_states"][CASE_ID] == ACTIVE_STATE
assert case["current_state"] == ACTIVE_STATE
assert case["release_candidate_ready"] is True
assert case["issued"] is False, case["issued"]
assert case["media_present"] is False, case["media_present"]

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION FUTURE SNAPSHOT FORK GATE: PASS")
print(f"RECORD_CURRENT_STATE={RECORD_STATE}")
print(f"ACTIVE_CURRENT_STATE={ACTIVE_STATE}")
print("FORK_SCOPE=FUTURE_VALID_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS_CREATE_NEW_SNAPSHOT_ONLY")
print("FUTURE_CONTINUITY_SEAL_PRESENT=true")
print("PERMANENCE_SEAL_PRESENT=true")
print("CURRENT_ZERO_ADMISSION_SNAPSHOT_PERMANENT=true")
print("CURRENT_ZERO_ADMISSION_SNAPSHOT_MUTABLE=false")
print("CURRENT_ZERO_ADMISSION_SNAPSHOT_REOPENABLE_BY_FUTURE_REQUEST=false")
print("FUTURE_VALID_ADMISSION_REQUESTS_CREATE_NEW_SNAPSHOT=true")
print("FUTURE_VALID_ADMISSION_REQUESTS_FORK_FROM_CURRENT_ZERO_SNAPSHOT=true")
print("FUTURE_VALID_ADMISSION_REQUESTS_DO_NOT_MUTATE_CURRENT_ZERO_SNAPSHOT=true")
print("FUTURE_VALID_ADMISSION_REQUESTS_DO_NOT_MUTATE_TERMINAL_SNAPSHOT=true")
print("CANONICAL_FIRST_FUTURE_AUTHORITY_SLOT_ID=director_final_cut_authority")
print("CANONICAL_FIRST_FUTURE_AUTHORITY_OBJECT=DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT")
print("FUTURE_SNAPSHOT_FORK_GATE_PASSED=false")
print("FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW=false")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ACTIVE_RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
