#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'RELEASE_CANDIDATE_READY'
CASE_ID = 'CASE_001_THE_LAST_RENDER'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

seal = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

for obj in (seal, law, status):
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == TARGET, obj
    assert obj["authority_object_admission_closure_seal_passed"] is True
    assert obj["admission_closed"] is True
    assert obj["authority_object_stack_complete"] is True, obj
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["release_candidate_ready"] is True, obj
    assert obj["release_candidate_artifacts_bound"] is False
    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False
    assert obj["admissibility_verdict_present"] is False
    assert obj["terminal_closure_present"] is False
    assert obj["next_required_object"] == "RELEASE_CANDIDATE_GAP_LEDGER", obj

assert index["active_case_states"][CASE_ID] == TARGET
assert case["current_state"] == TARGET
assert registry["current_active_state"] == TARGET, registry.get("current_active_state")

print("CINEMATICUM AUTHORITY OBJECT ADMISSION CLOSURE SEAL: PASS")
print(f"CURRENT_STATE={TARGET}")
print("ADMISSION_CLOSED=true")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=8")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=8")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=0")
print("RELEASE_CANDIDATE_READY=true")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
