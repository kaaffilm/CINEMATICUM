#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
ACTIVE_STATE = "RELEASE_CANDIDATE_READY"

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

ledger = load("RELEASE_CANDIDATE_READY_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
seal = load("RELEASE_CANDIDATE_READY_REPOSITORY_STATUS_SEAL.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert ledger["object_type"] == "RELEASE_CANDIDATE_READY_TRANSITION_ATTEMPT_REJECTION_LEDGER"
assert ledger["surface_type"] == "ACTIVE_RELEASE_CANDIDATE_READY_TRANSITION_ATTEMPT_REJECTION_LEDGER"
assert ledger["case_id"] == CASE_ID
assert ledger["active_current_state"] == ACTIVE_STATE
assert ledger["current_state"] == ACTIVE_STATE
assert index["active_case_states"][CASE_ID] == ACTIVE_STATE
assert case["current_state"] == ACTIVE_STATE
assert registry["current_active_state"] == ACTIVE_STATE
assert seal["next_required_object"] == "RELEASE_CANDIDATE_READY_TRANSITION_ATTEMPT_REJECTION_LEDGER"

for key in [
    "prior_required_object_present",
    "transition_attempt_rejection_ledger_present",
    "transition_attempt_rejection_ledger_sealed",
    "all_transition_attempts_rejected",
    "zero_transition_attempts_valid",
    "release_candidate_ready",
    "ledger_does_not_issue_motion_picture",
    "ledger_does_not_admit_media",
    "ledger_does_not_unblock_issuance",
    "ledger_does_not_advance_state",
    "ledger_does_not_create_valid_transition_attempt"
]:
    assert ledger[key] is True, key

for key in [
    "valid_transition_attempt_present",
    "may_advance_now",
    "issuance_unblocked",
    "issued",
    "media_present",
    "replay_passed"
]:
    assert ledger[key] is False, key

assert ledger["transition_attempts_recorded"] == 0
assert ledger["accepted_transition_attempt_count"] == 0
assert ledger["rejected_transition_attempt_count"] == 0
assert ledger["unadjudicated_transition_attempt_count"] == 0
assert ledger["prior_required_object"] == "RELEASE_CANDIDATE_READY_REPOSITORY_STATUS_SEAL"
assert ledger["next_required_object"] == "RELEASE_CANDIDATE_READY_ISSUANCE_BLOCKADE_SEAL"

print("CINEMATICUM RELEASE CANDIDATE READY TRANSITION ATTEMPT REJECTION LEDGER: PASS")
print("CURRENT_STATE=RELEASE_CANDIDATE_READY")
print("TRANSITION_ATTEMPTS_RECORDED=0")
print("VALID_TRANSITION_ATTEMPT_PRESENT=false")
print("RELEASE_CANDIDATE_READY=true")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("NEXT_REQUIRED_OBJECT=RELEASE_CANDIDATE_READY_ISSUANCE_BLOCKADE_SEAL")
PY2
