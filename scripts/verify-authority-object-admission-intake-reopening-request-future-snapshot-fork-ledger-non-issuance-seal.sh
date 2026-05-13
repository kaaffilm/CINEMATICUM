#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
ACTIVE_TARGET = 'ISSUED_ADMISSIBLE_MOTION_PICTURE'
CASE_ID = 'CASE_001_THE_LAST_RENDER'
PREFIX = 'AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEAL'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

seal = load(f"CINEMATICUM_{PREFIX}.json")
law = load(f"CINEMATICUM_{PREFIX}_LAW.json")
status = load(f"CASES/CASE_001_THE_LAST_RENDER/{PREFIX}_STATUS.json")
terminal = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_TERMINAL_CLOSURE_SEAL.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

for obj in (seal, law, status):
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == TARGET, "current_state=" + str(obj.get("current_state"))

    assert obj["future_snapshot_fork_ledger_terminal_closure_sealed"] is True
    assert obj["future_snapshot_fork_ledger_non_issuance_sealed"] is True
    assert obj["current_zero_ledger_non_issuing"] is True
    assert obj["current_zero_ledger_not_admissible_motion_picture"] is True
    assert obj["current_zero_ledger_not_release_candidate"] is True
    assert obj["current_zero_ledger_not_media_admission"] is True

    assert obj["future_snapshot_fork_gate_passed_now"] is False
    assert obj["future_snapshot_fork_gate_open_now"] is False
    assert obj["current_snapshot_final"] is True
    assert obj["current_snapshot_mutable"] is False
    assert obj["current_snapshot_forked_now"] is False
    assert obj["future_snapshot_fork_record_count"] == 0
    assert obj["new_snapshot_record_count"] == 0
    assert obj["no_new_snapshot_created_now"] is True

    assert obj["terminal_closure_does_not_issue_motion_picture"] is True
    assert obj["non_issuance_seal_passed_for_current_zero_ledger"] is True
    assert obj["non_issuance_seal_passed_for_future_fork"] is False
    assert obj["non_issuance_seal_does_not_open_future_fork_gate"] is True
    assert obj["non_issuance_seal_does_not_create_new_snapshot"] is True
    assert obj["non_issuance_seal_does_not_mutate_current_snapshot"] is True
    assert obj["non_issuance_seal_does_not_mutate_permanent_ledger"] is True
    assert obj["non_issuance_seal_does_not_satisfy_authority"] is True
    assert obj["non_issuance_seal_does_not_advance_state"] is True
    assert obj["non_issuance_seal_does_not_issue_motion_picture"] is True

    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False
    assert obj["release_candidate_ready"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["media_admitted"] is False
    assert isinstance(obj["outsider_replay_passed"], bool), "outsider_replay_passed"
    assert isinstance(obj["admissibility_verdict_present"], bool), "admissibility_verdict_present"
    assert isinstance(obj["terminal_closure_present"], bool), "terminal_closure_present"

    assert obj["authority_object_stack_complete"] is True
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["next_required_object"] == "RELEASE_CANDIDATE_GAP_LEDGER"

assert terminal["current_state"] == TARGET
assert terminal["future_snapshot_fork_ledger_terminal_closure_sealed"] is True

assert index["active_case_states"][CASE_ID] == ACTIVE_TARGET
assert case["current_state"] == ACTIVE_TARGET, case["current_state"]
assert registry["current_active_state"] in (ACTIVE_TARGET, "RELEASE_CANDIDATE_READY"), registry["current_active_state"]

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER NON-ISSUANCE SEAL: PASS")
print("CURRENT_STATE=" + TARGET)
print("NON_ISSUANCE_SCOPE=CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY")
print("FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEALED=true")
print("NON_ISSUANCE_SEAL_PASSED_FOR_CURRENT_ZERO_LEDGER=true")
print("NON_ISSUANCE_SEAL_PASSED_FOR_FUTURE_FORK=false")
print("NON_ISSUANCE_SEAL_DOES_NOT_OPEN_FUTURE_FORK_GATE=true")
print("NON_ISSUANCE_SEAL_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("NON_ISSUANCE_SEAL_DOES_NOT_MUTATE_CURRENT_SNAPSHOT=true")
print("NON_ISSUANCE_SEAL_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
