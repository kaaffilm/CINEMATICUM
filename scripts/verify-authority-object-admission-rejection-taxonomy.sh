#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json
test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_LAW.json
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_STATUS.json

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
ACTIVE_TARGET = 'RELEASE_CANDIDATE_READY'
CASE = 'CASE_001_THE_LAST_RENDER'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'
REQUEST_PATTERN = 'fixtures/authority_object_admission_requests/rejected/*.json'
FALSE_KEYS = ['admission_requests_present', 'valid_admission_request_present', 'invalid_admission_requests_present', 'accepted_admission_request_present', 'accepted_authority_request_present', 'release_candidate_ready', 'release_candidate_artifacts_bound', 'issued', 'media_present', 'outsider_replay_passed', 'admissibility_verdict_present', 'terminal_closure_present', 'may_advance_now', 'issuance_unblocked']

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

surface = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert surface["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_LAW"
assert status["status"] == "PASS"

for obj in (surface, law, status):
    assert obj["case_id"] == CASE
    assert obj["current_state"] == TARGET
    assert obj['admission_rejection_taxonomy_present'] is True
    assert obj["current_truth_owner"] is False
    assert obj["request_file_pattern"] == REQUEST_PATTERN
    assert obj["rejection_fixture_pattern"] == REQUEST_PATTERN
    assert obj["schema_non_authoritative"] is True
    assert obj["validator_non_authoritative"] is True
    assert obj["corpus_non_authoritative"] is True
    assert obj["taxonomy_non_authoritative"] is True
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
assert schema["current_state"] == TARGET
assert validator["current_state"] == TARGET

print("CINEMATICUM AUTHORITY OBJECT ADMISSION REJECTION TAXONOMY: PASS")
print(f"CURRENT_STATE={TARGET}")
print(f"REQUEST_FILE_PATTERN={REQUEST_PATTERN}")
print("ADMISSION_REQUESTS_PRESENT=false")
print("VALID_ADMISSION_REQUEST_PRESENT=false")
print("SCHEMA_NON_AUTHORITATIVE=true")
print("VALIDATOR_NON_AUTHORITATIVE=true")
print("CORPUS_NON_AUTHORITATIVE=true")
print("TAXONOMY_NON_AUTHORITATIVE=true")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("SCHEMAS_DO_NOT_SATISFY_AUTHORITY_OBJECTS=true")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
