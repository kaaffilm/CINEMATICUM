#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json
test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW.json
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_STATUS.json

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
ACTIVE_TARGET = 'ISSUED_ADMISSIBLE_MOTION_PICTURE'
CASE = 'CASE_001_THE_LAST_RENDER'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'
FALSE_KEYS = ['admission_requests_present', 'valid_admission_request_present', 'invalid_admission_requests_present', 'release_candidate_ready', 'release_candidate_artifacts_bound', 'issued', 'media_present', 'outsider_replay_passed', 'admissibility_verdict_present', 'terminal_closure_present', 'may_advance_now', 'issuance_unblocked']

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

surface = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
instantiation = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert surface["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW"
assert status["status"] == "PASS"

for obj in (surface, law, status):
    assert obj["case_id"] == CASE
    assert obj["current_state"] == TARGET
    assert obj['admission_request_schema_only'] is True
    assert obj["current_truth_owner"] is False
    assert obj["schema_non_authoritative"] is True
    assert obj["validator_non_authoritative"] is True
    assert obj["authority_object_stack_complete"] is True
    assert obj["required_authority_objects_missing"] is False
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["schemas_do_not_satisfy_authority_objects"] is True
    assert obj["next_required_object"] == NEXT_OBJECT
    for key in FALSE_KEYS:
        assert obj[key] is False, key

assert index["active_case_states"][CASE] == ACTIVE_TARGET, index["active_case_states"][CASE]
assert case["current_state"] == ACTIVE_TARGET, case["current_state"]
assert registry["current_active_state"] in (ACTIVE_TARGET, "RELEASE_CANDIDATE_READY"), registry["current_active_state"]
assert docket["current_state"] == TARGET
assert docket["authority_object_admission_docket_passed"] is True
assert instantiation["current_state"] == TARGET
assert instantiation["authority_object_instantiation_gate_passed"] is True

print("CINEMATICUM AUTHORITY OBJECT ADMISSION REQUEST SCHEMA: PASS")
print(f"CURRENT_STATE={TARGET}")
print("ADMISSION_REQUESTS_PRESENT=false")
print("VALID_ADMISSION_REQUEST_PRESENT=false")
print("SCHEMA_NON_AUTHORITATIVE=true")
print("VALIDATOR_NON_AUTHORITATIVE=true")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("SCHEMAS_DO_NOT_SATISFY_AUTHORITY_OBJECTS=true")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
