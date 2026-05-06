#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
NEXT = "RELEASE_CANDIDATE_ARTIFACTS_DOCKET"

paths = [
    "CINEMATICUM_RELEASE_CANDIDATE_GAP_LEDGER.json",
    "CINEMATICUM_RELEASE_CANDIDATE_GAP_LEDGER_LAW.json",
    f"CASES/{CASE_ID}/RELEASE_CANDIDATE_GAP_LEDGER/RELEASE_CANDIDATE_GAP_LEDGER.json",
    f"CASES/{CASE_ID}/RELEASE_CANDIDATE_GAP_LEDGER_STATUS.json",
]

objs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]

for obj in objs:
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == CURRENT_STATE
    assert obj["release_candidate_gap_ledger_present"] is True
    assert obj["release_candidate_gap_ledger_sealed"] is True
    assert obj["authority_object_stack_complete"] is True
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["future_authority_satisfaction_gate_passed"] is True
    assert obj["release_candidate_ready"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False
    assert obj["admissibility_verdict_present"] is False
    assert obj["terminal_closure_present"] is False
    assert obj["required_release_candidate_gap_count"] == 6
    assert obj["ledger_does_not_create_release_candidate"] is True
    assert obj["ledger_does_not_issue_motion_picture"] is True
    assert obj["ledger_does_not_admit_media"] is True
    assert obj["ledger_does_not_pass_outsider_replay"] is True
    assert obj["ledger_does_not_mutate_current_state"] is True
    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["next_required_object"] == NEXT

record = objs[2]
assert record["record_id"] == "GAP_001_RELEASE_CANDIDATE_ARTIFACTS"

print("CINEMATICUM RELEASE CANDIDATE GAP LEDGER: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=8")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=8")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=0")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("OUTSIDER_REPLAY_PASSED=false")
print("ADMISSIBILITY_VERDICT_PRESENT=false")
print("TERMINAL_CLOSURE_PRESENT=false")
print("REQUIRED_RELEASE_CANDIDATE_GAP_COUNT=6")
print(f"NEXT_REQUIRED_OBJECT={NEXT}")
PY
