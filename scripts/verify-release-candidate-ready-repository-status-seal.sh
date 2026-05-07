#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
ACTIVE_STATE = "RELEASE_CANDIDATE_READY"

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

seal = load("RELEASE_CANDIDATE_READY_REPOSITORY_STATUS_SEAL.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert seal["object_type"] == "RELEASE_CANDIDATE_READY_REPOSITORY_STATUS_SEAL"
assert seal["active_current_state"] == ACTIVE_STATE
assert index["active_case_states"][CASE_ID] == ACTIVE_STATE
assert case["current_state"] == ACTIVE_STATE
assert registry["current_active_state"] == ACTIVE_STATE

for key in [
    "release_candidate_ready_repository_status_seal_present",
    "repository_status_sealed",
    "release_candidate_ready",
    "verify_all_required",
    "registry_fresh_required",
    "status_seal_does_not_issue_motion_picture",
    "status_seal_does_not_admit_media",
    "status_seal_does_not_unblock_issuance"
]:
    assert seal[key] is True, key

for key in ["issued", "issuance_unblocked", "media_present", "replay_passed"]:
    assert seal[key] is False, key

assert seal["next_required_object"] == "RELEASE_CANDIDATE_READY_TRANSITION_ATTEMPT_REJECTION_LEDGER"

print("CINEMATICUM RELEASE CANDIDATE READY REPOSITORY STATUS SEAL: PASS")
print("ACTIVE_CURRENT_STATE=RELEASE_CANDIDATE_READY")
print("RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("ISSUANCE_UNBLOCKED=false")
print("MEDIA_PRESENT=false")
print("REPLAY_PASSED=false")
print("NEXT_REQUIRED_OBJECT=RELEASE_CANDIDATE_READY_TRANSITION_ATTEMPT_REJECTION_LEDGER")
PY2
