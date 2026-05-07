#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
ACTIVE_TARGET = 'RELEASE_CANDIDATE_READY'
CASE_ID = 'CASE_001_THE_LAST_RENDER'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR_STATUS.json")
schema_status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

for obj in (validator, law, status):
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == TARGET

    assert obj["authority_object_admission_intake_reopening_request_validator_passed"] is True
    assert obj["reopening_request_validator_present"] is True
    assert obj["reopening_request_validation_passed"] is True
    assert obj["validator_non_authoritative"] is True
    assert obj["reopening_request_validator_non_authoritative"] is True

    assert obj["schema_non_authoritative"] is True
    assert obj["reopening_request_schema_non_authoritative"] is True
    assert obj["schemas_do_not_satisfy_authority_objects"] is True
    assert obj["validator_does_not_satisfy_authority_objects"] is True
    assert obj["validator_does_not_reopen_current_snapshot"] is True
    assert obj["validator_does_not_create_new_snapshot"] is True
    assert obj["validator_does_not_accept_requests"] is True

    assert obj["intake_reopening_allowed"] is False
    assert obj["intake_accepts_reopening_requests"] is False
    assert obj["current_snapshot_reopened"] is False
    assert obj["new_snapshot_created"] is False

    assert obj["admission_requests_present"] is False
    assert obj["valid_admission_request_present"] is False
    assert obj["invalid_admission_request_present"] is False
    assert obj["live_admission_request_count"] == 0

    assert obj["reopening_request_present"] is False
    assert obj["valid_reopening_request_present"] is False
    assert obj["invalid_reopening_request_present"] is False
    assert obj["live_reopening_request_count"] == 0
    assert obj["accepted_reopening_request_count"] == 0
    assert obj["rejected_reopening_request_count"] == 0

    assert obj["authority_object_stack_complete"] is True
    assert obj["required_authority_objects_missing"] is False
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0

    assert obj["release_candidate_ready"] is False
    assert obj["release_candidate_artifacts_bound"] is False
    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    for evidence_key in (
        "outsider_replay_passed",
        "admissibility_verdict_present",
        "terminal_closure_present",
    ):
        assert isinstance(obj[evidence_key], bool), evidence_key
    assert obj["next_required_object"] == "RELEASE_CANDIDATE_GAP_LEDGER"

assert schema_status["current_state"] == TARGET
assert schema_status["reopening_request_schema_present"] is True
assert schema_status["schema_non_authoritative"] is True

assert index["active_case_states"][CASE_ID] == ACTIVE_TARGET
assert case["current_state"] == ACTIVE_TARGET
assert registry["current_active_state"] == ACTIVE_TARGET

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST VALIDATOR: PASS")
print("CURRENT_STATE=" + TARGET)
print("REOPENING_REQUEST_VALIDATOR_PRESENT=true")
print("REOPENING_REQUEST_VALIDATION_PASSED=true")
print("VALIDATOR_NON_AUTHORITATIVE=true")
print("REOPENING_REQUEST_PRESENT=false")
print("VALID_REOPENING_REQUEST_PRESENT=false")
print("INTAKE_REOPENING_ALLOWED=false")
print("CURRENT_SNAPSHOT_REOPENED=false")
print("NEW_SNAPSHOT_CREATED=false")
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
