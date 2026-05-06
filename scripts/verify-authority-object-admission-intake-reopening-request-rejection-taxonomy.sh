#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
CASE_ID = 'CASE_001_THE_LAST_RENDER'
REQUEST_PATTERN = 'fixtures/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS/*.json'
REASONS = ['wrong_current_state', 'media_present', 'missing_authority_object_manifest', 'silent_reopening_allowed']

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY_STATUS.json")
corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

for obj in (taxonomy, law, status):
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == TARGET

    assert obj["authority_object_admission_intake_reopening_request_rejection_taxonomy_passed"] is True
    assert obj["reopening_request_rejection_taxonomy_present"] is True
    assert obj["reopening_request_rejection_taxonomy_sealed"] is True
    assert obj["reopening_request_rejection_taxonomy_non_authoritative"] is True
    assert obj["taxonomy_non_authoritative"] is True
    assert obj["corpus_non_authoritative"] is True
    assert obj["schema_non_authoritative"] is True
    assert obj["validator_non_authoritative"] is True
    assert obj["schemas_do_not_satisfy_authority_objects"] is True
    assert obj["taxonomy_does_not_satisfy_authority_objects"] is True
    assert obj["taxonomy_does_not_reopen_current_snapshot"] is True
    assert obj["taxonomy_does_not_create_new_snapshot"] is True
    assert obj["taxonomy_does_not_accept_requests"] is True
    assert obj["taxonomy_does_not_reject_live_requests"] is True

    assert obj["request_file_pattern"] == REQUEST_PATTERN
    assert obj["canonical_rejection_reason_count"] == len(REASONS)
    assert obj["canonical_rejection_reasons"] == REASONS
    assert obj["fixture_count"] == 4
    assert obj["all_fixtures_rejected"] is True
    assert obj["fixtures_are_live_requests"] is False

    assert obj["reopening_request_present"] is False
    assert obj["valid_reopening_request_present"] is False
    assert obj["invalid_reopening_request_present"] is False
    assert obj["live_reopening_request_count"] == 0
    assert obj["accepted_reopening_request_count"] == 0
    assert obj["rejected_reopening_request_count"] == 0

    assert obj["intake_reopening_allowed"] is False
    assert obj["intake_accepts_reopening_requests"] is False
    assert obj["current_snapshot_reopened"] is False
    assert obj["new_snapshot_created"] is False

    assert obj["authority_object_stack_complete"] is True
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
    assert obj["outsider_replay_passed"] is False
    assert obj["admissibility_verdict_present"] is False
    assert obj["terminal_closure_present"] is False
    assert obj["next_required_object"] == "RELEASE_CANDIDATE_GAP_LEDGER"

assert corpus["current_state"] == TARGET
assert corpus["canonical_rejection_reasons"] == REASONS
assert corpus["all_fixtures_rejected"] is True

assert index["active_case_states"][CASE_ID] == TARGET
assert case["current_state"] == TARGET
assert registry["current_active_state"] == TARGET

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST REJECTION TAXONOMY: PASS")
print("CURRENT_STATE=" + TARGET)
print("REQUEST_FILE_PATTERN=" + REQUEST_PATTERN)
print("CANONICAL_REJECTION_REASON_COUNT=4")
print("REOPENING_REQUEST_PRESENT=false")
print("VALID_REOPENING_REQUEST_PRESENT=false")
print("CORPUS_NON_AUTHORITATIVE=true")
print("TAXONOMY_NON_AUTHORITATIVE=true")
print("ALL_FIXTURES_REJECTED=true")
print("FIXTURE_COUNT=4")
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
