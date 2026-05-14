#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
ACTIVE_TARGET = 'ISSUED_ADMISSIBLE_MOTION_PICTURE'
CASE_ID = 'CASE_001_THE_LAST_RENDER'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

order = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

for obj in (order, law, status):
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == TARGET
    assert obj["authority_object_admission_intake_order_passed"] is True
    assert obj["intake_order_closed"] is True
    assert obj["intake_accepts_new_requests"] is False
    assert obj["admission_requests_present"] is False
    assert obj["valid_admission_request_present"] is False
    assert obj["authority_object_stack_complete"] is True
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["schemas_do_not_satisfy_authority_objects"] is True
    assert obj["release_candidate_ready"] is False
    assert obj["release_candidate_artifacts_bound"] is False
    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False
    assert obj["admissibility_verdict_present"] is False
    assert obj["terminal_closure_present"] is False
    assert obj["next_required_object"] == "RELEASE_CANDIDATE_GAP_LEDGER"

assert index["active_case_states"][CASE_ID] == ACTIVE_TARGET
assert case["current_state"] == ACTIVE_TARGET, case["current_state"]
assert registry["current_active_state"] in (ACTIVE_TARGET, "RELEASE_CANDIDATE_READY"), registry["current_active_state"]

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE ORDER: PASS")
print(f"CURRENT_STATE={TARGET}")
print("INTAKE_ORDER_CLOSED=true")
print("INTAKE_ACCEPTS_NEW_REQUESTS=false")
print("ADMISSION_REQUESTS_PRESENT=false")
print("VALID_ADMISSION_REQUEST_PRESENT=false")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=8")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=8")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=0")
print("RELEASE_CANDIDATE_READY=false")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
