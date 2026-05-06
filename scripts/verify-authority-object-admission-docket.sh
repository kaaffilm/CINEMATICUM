#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json
test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET_LAW.json
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_DOCKET_STATUS.json

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
CASE = 'CASE_001_THE_LAST_RENDER'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'
FALSE_KEYS = ['release_candidate_ready', 'release_candidate_artifacts_bound', 'issued', 'media_present', 'outsider_replay_passed', 'admissibility_verdict_present', 'terminal_closure_present', 'may_advance_now', 'issuance_unblocked']

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_DOCKET_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
required = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
instantiation = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert docket["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET_LAW"
assert status["status"] == "PASS"

for obj in (docket, law, status):
    assert obj["case_id"] == CASE
    assert obj["current_state"] == TARGET
    assert obj["authority_object_admission_docket_passed"] is True
    assert obj["authority_objects_admitted"] is True
    assert obj["authority_object_stack_complete"] is True
    assert obj["required_authority_objects_missing"] is False
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["schemas_do_not_satisfy_authority_objects"] is True
    assert obj["next_required_object"] == NEXT_OBJECT
    for key in FALSE_KEYS:
        assert obj[key] is False, key

assert index["active_case_states"][CASE] == TARGET
assert case["current_state"] == TARGET
assert registry["current_active_state"] == TARGET
assert required["current_state"] == TARGET
assert required["authority_object_stack_complete"] is True
assert instantiation["current_state"] == TARGET
assert instantiation["authority_object_instantiation_gate_passed"] is True
assert instantiation["instantiated_authority_object_count"] == 8

print("CINEMATICUM AUTHORITY OBJECT ADMISSION DOCKET: PASS")
print(f"CURRENT_STATE={TARGET}")
print("AUTHORITY_OBJECT_ADMISSION_DOCKET_PASSED=true")
print("AUTHORITY_OBJECTS_ADMITTED=true")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=8")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=8")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=0")
print("SCHEMAS_DO_NOT_SATISFY_AUTHORITY_OBJECTS=true")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
