#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
CASE_ID = 'CASE_001_THE_LAST_RENDER'
PREFIX = 'AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_TERMINAL_CLOSURE_SEAL'

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
    for key in ['current_zero_ledger_closed_against_reclassification', 'current_zero_ledger_terminally_closed', 'future_snapshot_fork_ledger_outsider_replay_sealed', 'future_snapshot_fork_ledger_terminal_closure_sealed', 'terminal_closure_does_not_create_new_snapshot', 'terminal_closure_does_not_mutate_current_snapshot', 'terminal_closure_does_not_mutate_permanent_ledger', 'terminal_closure_does_not_open_future_fork_gate', 'terminal_closure_seal_passed_for_current_zero_ledger']:
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
    assert obj["outsider_replay_passed"] is False
    assert obj["admissibility_verdict_present"] is False
    assert obj["terminal_closure_present"] is False

    assert obj["authority_object_stack_complete"] is True
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["next_required_object"] == "RELEASE_CANDIDATE_GAP_LEDGER"

assert index["active_case_states"][CASE_ID] == TARGET
assert case["current_state"] == TARGET
assert registry["current_active_state"] == TARGET

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER TERMINAL CLOSURE SEAL: PASS")
print("CURRENT_STATE=" + TARGET)
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
