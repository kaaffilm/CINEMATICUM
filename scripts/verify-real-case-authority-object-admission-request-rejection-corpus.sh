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

def maybe_load(path):
    p = Path(path)
    return load(path) if p.exists() else None

root = maybe_load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
law = maybe_load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

records = [obj for obj in (root, law, status) if obj is not None]

for obj in records:
    if "case_id" in obj:
        assert obj["case_id"] == CASE_ID
    if "current_state" in obj:
        assert obj["current_state"] == RECORD_STATE, obj["current_state"]

    if "corpus_scope" in obj:
        assert obj["corpus_scope"] == "REAL_CASE_AUTHORITY_OBJECTS_ONLY"
    if "real_case_authority_object_admission_request_rejection_corpus_present" in obj:
        assert obj["real_case_authority_object_admission_request_rejection_corpus_present"] is True
    if "real_case_authority_object_admission_request_rejection_corpus_sealed" in obj:
        assert obj["real_case_authority_object_admission_request_rejection_corpus_sealed"] is True

    for key in (
        "fixtures_are_live_requests",
        "corpus_does_not_create_live_requests",
        "corpus_does_not_accept_requests",
        "corpus_does_not_reject_live_requests",
        "corpus_does_not_instantiate_authority_objects",
        "corpus_does_not_satisfy_authority",
        "corpus_does_not_advance_state",
        "corpus_does_not_issue_motion_picture",
        "corpus_does_not_admit_media",
        "corpus_does_not_create_release_candidate",
        "corpus_does_not_reopen_current_snapshot",
        "corpus_does_not_create_new_snapshot",
    ):
        if key in obj:
            expected = False if key == "fixtures_are_live_requests" else True
            assert obj[key] is expected, f"{key}={obj[key]}"

    for key in (
        "live_admission_request_count",
        "valid_admission_request_count",
        "accepted_admission_request_count",
        "accepted_authority_object_count",
        "instantiated_authority_object_count",
    ):
        if key in obj:
            assert obj[key] == 0, f"{key}={obj[key]}"

    if "rejection_fixture_count" in obj:
        assert obj["rejection_fixture_count"] >= 1
    if "all_fixtures_rejected" in obj:
        assert obj["all_fixtures_rejected"] is True

    for key in (
        "authority_satisfied",
        "may_advance_now",
        "issued",
        "media_present",
    ):
        if key in obj:
            assert obj[key] is False, f"{key}={obj[key]}"

    # Historical corpus record remains non-capability even after active state advances.
    if "release_candidate_ready" in obj:
        assert obj["release_candidate_ready"] is False, f"record.release_candidate_ready={obj[key]}"

assert index["active_case_states"][CASE_ID] == ACTIVE_STATE
assert index["active_current_state"] == ACTIVE_STATE
assert case["current_state"] == ACTIVE_STATE
assert case["release_candidate_ready"] is True
assert case["issued"] is False, case["issued"]
assert case["media_present"] is False, case["media_present"]

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REQUEST REJECTION CORPUS: PASS")
print(f"RECORD_CURRENT_STATE={RECORD_STATE}")
print(f"ACTIVE_CURRENT_STATE={ACTIVE_STATE}")
print("CORPUS_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("FIXTURES_ARE_LIVE_REQUESTS=false")
print("LIVE_ADMISSION_REQUEST_COUNT=0")
print("VALID_ADMISSION_REQUEST_COUNT=0")
print("ACCEPTED_ADMISSION_REQUEST_COUNT=0")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("ALL_FIXTURES_REJECTED=true")
print("CORPUS_DOES_NOT_CREATE_LIVE_REQUESTS=true")
print("CORPUS_DOES_NOT_SATISFY_AUTHORITY=true")
print("CORPUS_DOES_NOT_ADVANCE_STATE=true")
print("CORPUS_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("CORPUS_DOES_NOT_ADMIT_MEDIA=true")
print("RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
