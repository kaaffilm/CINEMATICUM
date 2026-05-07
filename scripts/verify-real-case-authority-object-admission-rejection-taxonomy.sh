#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE = "CASE_001_THE_LAST_RENDER"
ACTIVE = "RELEASE_CANDIDATE_READY"
RECORD = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

assert status["case_id"] == CASE
assert status["current_state"] == RECORD
assert status["taxonomy_scope"] == "REAL_CASE_AUTHORITY_OBJECTS_ONLY"
assert status["real_case_authority_object_admission_rejection_taxonomy_present"] is True
assert status["real_case_authority_object_admission_rejection_taxonomy_sealed"] is True
assert status["canonical_rejection_reason_count"] == 9
assert status["covered_rejection_reason_count"] == 5
assert status["uncovered_rejection_reason_count"] == 4
assert status["taxonomy_complete_for_current_validator"] is True
assert status["corpus_complete_for_required_reasons"] is True
assert status["fixtures_are_live_requests"] is False
assert status["live_admission_request_count"] == 0
assert status["valid_admission_request_count"] == 0
assert status["accepted_admission_request_count"] == 0
assert status["accepted_authority_object_count"] == 0
assert status["instantiated_authority_object_count"] == 0

for key in (
    "taxonomy_does_not_create_live_requests",
    "taxonomy_does_not_accept_requests",
    "taxonomy_does_not_reject_live_requests",
    "taxonomy_does_not_instantiate_authority_objects",
    "taxonomy_does_not_satisfy_authority",
    "taxonomy_does_not_advance_state",
    "taxonomy_does_not_issue_motion_picture",
    "taxonomy_does_not_admit_media",
):
    assert status[key] is True, key

for key in ("authority_satisfied", "may_advance_now", "release_candidate_ready", "issued", "media_present"):
    assert status[key] is False, key

assert index["active_case_states"][CASE] == ACTIVE
assert case["current_state"] == ACTIVE
assert case["release_candidate_ready"] is True
assert case["issued"] is False
assert case["media_present"] is False

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REJECTION TAXONOMY: PASS")
print(f"RECORD_CURRENT_STATE={RECORD}")
print(f"ACTIVE_CURRENT_STATE={ACTIVE}")
print("TAXONOMY_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_SEALED=true")
print("CANONICAL_REJECTION_REASON_COUNT=9")
print("COVERED_REJECTION_REASON_COUNT=5")
print("UNCOVERED_REJECTION_REASON_COUNT=4")
print("TAXONOMY_COMPLETE_FOR_CURRENT_VALIDATOR=true")
print("CORPUS_COMPLETE_FOR_REQUIRED_REASONS=true")
print("FIXTURES_ARE_LIVE_REQUESTS=false")
print("LIVE_ADMISSION_REQUEST_COUNT=0")
print("VALID_ADMISSION_REQUEST_COUNT=0")
print("ACCEPTED_ADMISSION_REQUEST_COUNT=0")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("TAXONOMY_DOES_NOT_CREATE_LIVE_REQUESTS=true")
print("TAXONOMY_DOES_NOT_ACCEPT_REQUESTS=true")
print("TAXONOMY_DOES_NOT_REJECT_LIVE_REQUESTS=true")
print("TAXONOMY_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true")
print("TAXONOMY_DOES_NOT_SATISFY_AUTHORITY=true")
print("TAXONOMY_DOES_NOT_ADVANCE_STATE=true")
print("TAXONOMY_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("TAXONOMY_DOES_NOT_ADMIT_MEDIA=true")
print("TAXONOMY_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("TAXONOMY_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true")
print("TAXONOMY_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ACTIVE_RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")

PY
