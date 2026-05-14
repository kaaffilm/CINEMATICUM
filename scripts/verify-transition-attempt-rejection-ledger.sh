#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

TARGET = "RELEASE_CANDIDATE_READY"
CASE_ID = "CASE_001_THE_LAST_RENDER"

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/TRANSITION_ATTEMPT_REJECTION_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

assert index["active_case_states"][CASE_ID] == TARGET
assert case["current_state"] == index["active_case_states"][CASE_ID]

for obj in (ledger, status):
    if "case_id" in obj:
        assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == TARGET
    assert obj["transition_attempts_recorded"] == 0
    assert obj["valid_transition_attempt_present"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["release_candidate_ready"] is True

print("CINEMATICUM TRANSITION ATTEMPT REJECTION LEDGER: PASS")
print(f"CURRENT_STATE={TARGET}")
print("TRANSITION_ATTEMPTS_RECORDED=0")
print("VALID_TRANSITION_ATTEMPT_PRESENT=false")
print("RELEASE_CANDIDATE_READY=true")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
