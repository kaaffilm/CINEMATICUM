#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json
test -f CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST_LAW.json
test -f CASES/CASE_001_THE_LAST_RENDER/REQUIRED_AUTHORITY_OBJECTS_STATUS.json

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'
CASE = 'CASE_001_THE_LAST_RENDER'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
law = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/REQUIRED_AUTHORITY_OBJECTS_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

assert checklist["object_type"] == "CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST"
assert law["object_type"] == "CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST_LAW"
assert status["status"] == "PASS"

for obj in (checklist, law, status):
    assert obj["case_id"] == CASE
    assert obj["current_state"] == TARGET
    assert obj["authority_object_stack_complete"] is True
    assert obj["required_authority_objects_missing"] is False
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
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

assert checklist["future_authority_satisfaction_gate_passed"] is True
assert checklist["schemas_do_not_satisfy_authority_objects"] is True
assert index["active_case_states"][CASE] == TARGET
assert case["current_state"] == TARGET

candidate = checklist["transition_candidates"][0]
assert candidate["from_state"] == TARGET
assert candidate["required_object"] == NEXT_OBJECT
assert candidate["may_advance_now"] is False
assert candidate["blocked"] is True

print("CINEMATICUM REQUIRED AUTHORITY OBJECT CHECKLIST: PASS")
print(f"CURRENT_STATE={TARGET}")
print("REQUIRED_AUTHORITY_OBJECTS_MISSING=false")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=8")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=8")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=0")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
