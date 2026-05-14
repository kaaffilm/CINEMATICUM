#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
ACTIVE_TARGET = 'RELEASE_CANDIDATE_READY'
CASE_ID = 'CASE_001_THE_LAST_RENDER'
PREFIX = 'AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_OUTSIDER_REPLAY_SEAL'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

objs = [
    load(f"CINEMATICUM_{PREFIX}.json"),
    load(f"CINEMATICUM_{PREFIX}_LAW.json"),
    load(f"CASES/CASE_001_THE_LAST_RENDER/{PREFIX}_STATUS.json"),
]
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

for obj in objs:
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == TARGET, "current_state=" + str(obj.get("current_state"))
    for key in ['future_snapshot_fork_ledger_outsider_replay_sealed', 'outsider_replay_does_not_create_new_snapshot', 'outsider_replay_does_not_mutate_current_snapshot', 'outsider_replay_does_not_mutate_permanent_ledger', 'outsider_replay_does_not_open_future_fork_gate', 'outsider_replay_seal_passed_for_current_zero_ledger']:
        assert obj[key] is True, key

    assert obj["future_snapshot_fork_gate_passed_now"] is False
    assert obj["future_snapshot_fork_gate_open_now"] is False
    assert obj["current_snapshot_final"] is True
    assert obj["current_snapshot_mutable"] is False
    assert obj["future_snapshot_fork_record_count"] == 0
    assert obj["new_snapshot_record_count"] == 0

    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False
    assert obj["release_candidate_ready"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["media_admitted"] is False
    for evidence_key in (
        "outsider_replay_passed",
        "admissibility_verdict_present",
        "terminal_closure_present",
    ):
        assert isinstance(obj[evidence_key], bool), evidence_key

    assert obj["authority_object_stack_complete"] is True
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["next_required_object"] == "RELEASE_CANDIDATE_GAP_LEDGER"

assert index["active_case_states"][CASE_ID] == ACTIVE_TARGET
assert case["current_state"] == ACTIVE_TARGET, case["current_state"]
assert registry["current_active_state"] in (ACTIVE_TARGET, "RELEASE_CANDIDATE_READY"), registry["current_active_state"]

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER OUTSIDER REPLAY SEAL: PASS")
print("CURRENT_STATE=" + TARGET)
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
