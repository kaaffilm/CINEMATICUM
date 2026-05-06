#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json
test -f CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LAW.json
test -f CASES/CASE_001_THE_LAST_RENDER/TRANSITION_ATTEMPT_REJECTION_STATUS.json

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
CASE = 'CASE_001_THE_LAST_RENDER'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
law = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/TRANSITION_ATTEMPT_REJECTION_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
required = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")

assert ledger["object_type"] == "CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER"
assert law["object_type"] == "CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LAW"
assert status["status"] == "PASS"

for obj in (ledger, law, status):
    assert obj["case_id"] == CASE
    assert obj["current_state"] == TARGET
    assert obj["transition_attempts_recorded"] == 0
    assert obj["valid_transition_attempt_present"] is False
    assert obj["release_candidate_ready"] is False
    assert obj["release_candidate_artifacts_bound"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False
    assert obj["admissibility_verdict_present"] is False
    assert obj["terminal_closure_present"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False
    assert obj["next_required_object"] == NEXT_OBJECT

assert ledger["authority_object_stack_complete"] is True
assert ledger["required_authority_objects_missing"] is False
assert ledger["accepted_authority_object_count"] == 8
assert ledger["instantiated_authority_object_count"] == 8
assert ledger["unfilled_authority_object_slot_count"] == 0
assert ledger["rejection_reason"] == "no_transition_attempt_present"

assert index["active_case_states"][CASE] == TARGET
assert case["current_state"] == TARGET
assert gate["current_state"] == TARGET
assert gate["may_advance_now"] is False
assert required["current_state"] == TARGET
assert required["may_advance_now"] is False

print("CINEMATICUM TRANSITION ATTEMPT REJECTION LEDGER: PASS")
print(f"CURRENT_STATE={TARGET}")
print("TRANSITION_ATTEMPTS_RECORDED=0")
print("VALID_TRANSITION_ATTEMPT_PRESENT=false")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
