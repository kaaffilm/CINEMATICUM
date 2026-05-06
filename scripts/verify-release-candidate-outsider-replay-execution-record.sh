#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
NEXT = "RELEASE_CANDIDATE_OUTSIDER_REPLAY_PASSAGE_RECORD"

paths = [
    "CINEMATICUM_RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD.json",
    "CINEMATICUM_RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD_LAW.json",
    f"CASES/{CASE_ID}/RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD/RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD.json",
    f"CASES/{CASE_ID}/RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD_STATUS.json",
]

objs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]

for obj in objs:
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == CURRENT_STATE
    assert obj["release_candidate_gap_ledger_present"] is True
    assert obj["release_candidate_artifacts_docket_present"] is True
    assert obj["release_candidate_manifest_present"] is True
    assert obj["release_candidate_evidence_bundle_present"] is True
    assert obj["release_candidate_public_inspection_dossier_present"] is True
    assert obj["release_candidate_outsider_replay_plan_present"] is True
    assert obj["release_candidate_terminal_closure_plan_present"] is True
    assert obj["release_candidate_planning_perimeter_complete"] is True
    assert obj["all_required_release_candidate_gap_objects_present"] is True

    assert obj["release_candidate_outsider_replay_execution_record_present"] is True
    assert obj["release_candidate_outsider_replay_execution_record_sealed"] is True
    assert obj["outsider_replay_execution_record_present"] is True
    assert obj["outsider_replay_execution_record_sealed"] is True
    assert obj["outsider_replay_execution_declared"] is True
    assert obj["outsider_replay_execution_completed"] is True
    assert obj["outsider_replay_execution_command"] == "bash scripts/verify-all.sh"
    assert obj["outsider_replay_execution_result"] == "PASS"

    assert obj["fresh_checkout_can_verify"] is True
    assert obj["private_access_required"] is False
    assert obj["network_required_after_clone"] is False
    assert obj["media_or_model_payload_present"] is False
    assert obj["forbidden_private_file_present"] is False

    assert obj["authority_object_stack_complete"] is True
    assert obj["future_authority_satisfaction_gate_passed"] is True
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0

    assert obj["outsider_replay_plan_declared"] is True
    assert obj["outsider_replay_passage_record_present"] is False
    assert obj["admissibility_verdict_record_present"] is False
    assert obj["terminal_closure_record_present"] is False

    assert obj["release_candidate_ready"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False
    assert obj["admissibility_verdict_present"] is False
    assert obj["terminal_closure_present"] is False
    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False

    assert obj["execution_record_is_not_passage_record"] is True
    assert obj["execution_record_does_not_pass_outsider_replay"] is True
    assert obj["execution_record_does_not_create_admissibility_verdict"] is True
    assert obj["execution_record_does_not_create_terminal_closure"] is True
    assert obj["execution_record_does_not_create_release_candidate"] is True
    assert obj["execution_record_does_not_issue_motion_picture"] is True
    assert obj["execution_record_does_not_admit_media"] is True
    assert obj["execution_record_does_not_mutate_current_state"] is True

    assert obj["required_remaining_release_candidate_gap_count"] == 0
    assert obj["next_required_object"] == NEXT

record = objs[2]
assert record["record_id"] == "OUTSIDER_REPLAY_EXECUTION_RECORD_001_RELEASE_CANDIDATE"

print("CINEMATICUM RELEASE CANDIDATE OUTSIDER REPLAY EXECUTION RECORD: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("RELEASE_CANDIDATE_PLANNING_PERIMETER_COMPLETE=true")
print("ALL_REQUIRED_RELEASE_CANDIDATE_GAP_OBJECTS_PRESENT=true")
print("RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD_PRESENT=true")
print("OUTSIDER_REPLAY_EXECUTION_DECLARED=true")
print("OUTSIDER_REPLAY_EXECUTION_COMPLETED=true")
print("OUTSIDER_REPLAY_EXECUTION_RESULT=PASS")
print("FRESH_CHECKOUT_CAN_VERIFY=true")
print("PRIVATE_ACCESS_REQUIRED=false")
print("NETWORK_REQUIRED_AFTER_CLONE=false")
print("MEDIA_OR_MODEL_PAYLOAD_PRESENT=false")
print("OUTSIDER_REPLAY_PASSAGE_RECORD_PRESENT=false")
print("ADMISSIBILITY_VERDICT_RECORD_PRESENT=false")
print("TERMINAL_CLOSURE_RECORD_PRESENT=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("OUTSIDER_REPLAY_PASSED=false")
print("ADMISSIBILITY_VERDICT_PRESENT=false")
print("TERMINAL_CLOSURE_PRESENT=false")
print(f"NEXT_REQUIRED_OBJECT={NEXT}")
PY
