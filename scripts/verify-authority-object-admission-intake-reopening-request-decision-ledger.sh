#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
CASE_ID = 'CASE_001_THE_LAST_RENDER'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

ledger = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER_STATUS.json")
schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA.json")
validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR.json")
taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

for obj in (ledger, law, status):
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == TARGET

    assert obj["authority_object_admission_intake_reopening_request_decision_ledger_passed"] is True
    assert obj["reopening_request_decision_ledger_present"] is True
    assert obj["reopening_request_decision_ledger_sealed"] is True
    assert obj["decision_ledger_non_authoritative"] is True
    assert obj["ledger_non_authoritative"] is True
    assert obj["schema_non_authoritative"] is True
    assert obj["validator_non_authoritative"] is True
    assert obj["corpus_non_authoritative"] is True
    assert obj["taxonomy_non_authoritative"] is True
    assert obj["schemas_do_not_satisfy_authority_objects"] is True
    assert obj["ledger_does_not_satisfy_authority_objects"] is True
    assert obj["ledger_does_not_reopen_current_snapshot"] is True
    assert obj["ledger_does_not_create_new_snapshot"] is True
    assert obj["ledger_does_not_accept_requests"] is True

    assert obj["reopening_request_present"] is False
    assert obj["valid_reopening_request_present"] is False
    assert obj["invalid_reopening_request_present"] is False
    assert obj["live_reopening_request_count"] == 0
    assert obj["decision_record_count"] == 0
    assert obj["accepted_decision_count"] == 0
    assert obj["rejected_decision_count"] == 0
    assert obj["all_live_reopening_requests_have_decisions"] is True
    assert obj["all_live_requests_have_decisions"] is True
    assert obj["no_decision_without_live_request"] is True

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

for upstream in (schema, validator, taxonomy):
    assert upstream["current_state"] == TARGET
    assert upstream["reopening_request_present"] is False
    assert upstream["valid_reopening_request_present"] is False

assert index["active_case_states"][CASE_ID] == TARGET
assert case["current_state"] == TARGET
assert registry["current_active_state"] == TARGET

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST DECISION LEDGER: PASS")
print("CURRENT_STATE=" + TARGET)
print("REOPENING_REQUEST_PRESENT=false")
print("VALID_REOPENING_REQUEST_PRESENT=false")
print("DECISION_RECORD_COUNT=0")
print("ACCEPTED_DECISION_COUNT=0")
print("REJECTED_DECISION_COUNT=0")
print("ALL_LIVE_REOPENING_REQUESTS_HAVE_DECISIONS=true")
print("LEDGER_NON_AUTHORITATIVE=true")
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
