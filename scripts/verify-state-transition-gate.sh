#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_STATE_TRANSITION_GATE.json
test -f CINEMATICUM_STATE_TRANSITION_GATE_LAW.json
test -f CASES/CASE_001_THE_LAST_RENDER/STATE_TRANSITION_GATE_STATUS.json

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'RELEASE_CANDIDATE_READY'
NEXT = 'RELEASE_CANDIDATE_ARTIFACTS_BOUND'
CASE = 'CASE_001_THE_LAST_RENDER'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
law = load("CINEMATICUM_STATE_TRANSITION_GATE_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/STATE_TRANSITION_GATE_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

assert gate["object_type"] == "CINEMATICUM_STATE_TRANSITION_GATE"
assert law["object_type"] == "CINEMATICUM_STATE_TRANSITION_GATE_LAW"
assert status["status"] == "PASS"

for obj in (gate, law, status):
    assert obj["case_id"] == CASE
    assert obj["current_state"] == TARGET
    assert obj["from_state"] == TARGET
    assert obj["next_required_state"] == NEXT
    assert obj["next_required_object"] == "RELEASE_CANDIDATE_GAP_LEDGER"
    assert obj["release_candidate_ready"] is True
    assert obj["release_candidate_artifacts_bound"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False
    assert obj["admissibility_verdict_present"] is False
    assert obj["terminal_closure_present"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False

assert gate["authority_object_stack_complete"] is True
assert gate["accepted_authority_object_count"] == 8
assert gate["instantiated_authority_object_count"] == 8
assert gate["unfilled_authority_object_slot_count"] == 0

assert index["active_case_states"][CASE] == "RELEASE_CANDIDATE_READY"
assert case["current_state"] == "RELEASE_CANDIDATE_READY"

candidate = gate["transition_candidates"][0]
assert candidate["from_state"] == TARGET
assert candidate["to_state"] == NEXT
assert candidate["may_advance_now"] is False
assert candidate["blocked"] is True

print("CINEMATICUM STATE TRANSITION GATE: PASS")
print(f"CURRENT_STATE={TARGET}")
print("RELEASE_CANDIDATE_READY=true")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
