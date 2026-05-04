#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

UPPER = "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_AUTHORITY_SATISFACTION_SEAL"
OBJECT = Path(f"CINEMATICUM_{UPPER}.json")
LAW = Path(f"CINEMATICUM_{UPPER}_LAW.json")
STATUS = Path(f"CASES/{CASE_ID}/{UPPER}_STATUS.json")

PREV_STATUS = Path(f"CASES/{CASE_ID}/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEAL_STATUS.json")
PREV_OBJECT = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEAL.json")

def load(path: Path):
    assert path.exists(), f"missing {path}"
    return json.loads(path.read_text())

obj = load(OBJECT)
law = load(LAW)
status = load(STATUS)
prev_status = load(PREV_STATUS)
prev_object = load(PREV_OBJECT)

assert prev_status["future_snapshot_fork_ledger_non_issuance_sealed"] is True
assert prev_status["non_issuance_seal_passed_for_current_zero_ledger"] is True
assert prev_status["authority_satisfied"] is False
assert prev_status["may_advance_now"] is False
assert prev_status["issued"] is False
assert prev_status["media_present"] is False
assert prev_object["future_snapshot_fork_ledger_non_issuance_sealed"] is True

for record in (obj, status):
    assert record["institution"] == "CINEMATICUM"
    assert record["root_sentence"] == "CINEMATICUM issues admissible motion pictures."
    assert record["case_id"] == CASE_ID
    assert record["current_state"] == CURRENT_STATE
    assert record["non_authority_satisfaction_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
    assert record["terminal_closure_scope_preserved"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
    assert record["non_issuance_scope_preserved"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
    assert record["future_snapshot_fork_ledger_present"] is True
    assert record["future_snapshot_fork_ledger_terminal_closure_sealed"] is True
    assert record["future_snapshot_fork_ledger_non_issuance_sealed"] is True
    assert record["future_snapshot_fork_ledger_non_authority_satisfaction_sealed"] is True
    assert record["current_zero_ledger_does_not_satisfy_authority"] is True
    assert record["current_zero_ledger_authority_satisfied"] is False
    assert record["current_zero_ledger_may_advance_now"] is False
    assert record["current_zero_ledger_release_candidate_ready"] is False
    assert record["current_zero_ledger_issued"] is False
    assert record["current_zero_ledger_media_present"] is False
    assert record["future_snapshot_fork_gate_passed_now"] is False
    assert record["future_snapshot_fork_gate_open_now"] is False
    assert record["future_snapshot_fork_record_count"] == 0
    assert record["new_snapshot_record_count"] == 0
    assert record["terminal_closure_does_not_satisfy_authority"] is True
    assert record["non_issuance_does_not_satisfy_authority"] is True
    assert record["non_authority_satisfaction_seal_passed_for_current_zero_ledger"] is True
    assert record["non_authority_satisfaction_seal_passed_for_future_fork"] is False
    assert record["non_authority_satisfaction_artifact_required_for_future_fork"] is True
    assert record["non_authority_satisfaction_artifact_present_for_future_fork"] is False
    assert record["non_authority_satisfaction_seal_does_not_open_future_fork_gate"] is True
    assert record["non_authority_satisfaction_seal_does_not_create_new_snapshot"] is True
    assert record["non_authority_satisfaction_seal_does_not_mutate_current_snapshot"] is True
    assert record["non_authority_satisfaction_seal_does_not_mutate_permanent_ledger"] is True
    assert record["non_authority_satisfaction_seal_does_not_satisfy_authority"] is True
    assert record["non_authority_satisfaction_seal_does_not_advance_state"] is True
    assert record["future_valid_fork_must_satisfy_authority_independently"] is True
    assert record["future_valid_fork_authority_satisfaction_must_target_new_snapshot"] is True
    assert record["private_access_required"] is False
    assert record["network_required_after_clone"] is False
    assert record["media_or_model_payload_present"] is False
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["issued"] is False
    assert record["media_present"] is False

assert law["requires_terminal_closure_seal"] is True
assert law["requires_non_issuance_seal"] is True
assert law["declares_current_zero_ledger_does_not_satisfy_authority"] is True
assert law["declares_current_zero_ledger_cannot_advance_state"] is True
assert law["declares_non_issuance_does_not_satisfy_authority"] is True
assert law["declares_terminal_closure_does_not_satisfy_authority"] is True
assert law["future_valid_fork_must_satisfy_authority_independently"] is True
assert law["future_valid_fork_authority_satisfaction_must_target_new_snapshot"] is True
assert law["silent_authority_satisfaction_forbidden"] is True
assert law["silent_state_advancement_forbidden"] is True
assert law["law_does_not_open_future_fork_gate"] is True
assert law["law_does_not_create_new_snapshot"] is True
assert law["law_does_not_mutate_current_snapshot"] is True
assert law["law_does_not_mutate_permanent_ledger"] is True
assert law["law_does_not_issue_motion_picture"] is True
assert law["authority_satisfied"] is False
assert law["may_advance_now"] is False
assert law["issued"] is False
assert law["media_present"] is False

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER NON-AUTHORITY-SATISFACTION SEAL: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("NON_AUTHORITY_SATISFACTION_SCOPE=CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY")
print("TERMINAL_CLOSURE_SCOPE_PRESERVED=CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY")
print("NON_ISSUANCE_SCOPE_PRESERVED=CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY")
for key in [
    "future_snapshot_fork_ledger_present",
    "future_snapshot_fork_ledger_terminal_closure_sealed",
    "future_snapshot_fork_ledger_non_issuance_sealed",
    "future_snapshot_fork_ledger_non_authority_satisfaction_sealed",
    "current_zero_ledger_does_not_satisfy_authority",
    "current_zero_ledger_authority_satisfied",
    "current_zero_ledger_may_advance_now",
    "current_zero_ledger_release_candidate_ready",
    "current_zero_ledger_issued",
    "current_zero_ledger_media_present",
    "future_snapshot_fork_gate_passed_now",
    "future_snapshot_fork_gate_open_now",
    "future_snapshot_fork_record_count",
    "new_snapshot_record_count",
    "terminal_closure_does_not_satisfy_authority",
    "non_issuance_does_not_satisfy_authority",
    "non_authority_satisfaction_seal_passed_for_current_zero_ledger",
    "non_authority_satisfaction_seal_passed_for_future_fork",
    "non_authority_satisfaction_artifact_required_for_future_fork",
    "non_authority_satisfaction_artifact_present_for_future_fork",
    "non_authority_satisfaction_seal_does_not_open_future_fork_gate",
    "non_authority_satisfaction_seal_does_not_create_new_snapshot",
    "non_authority_satisfaction_seal_does_not_mutate_current_snapshot",
    "non_authority_satisfaction_seal_does_not_mutate_permanent_ledger",
    "non_authority_satisfaction_seal_does_not_satisfy_authority",
    "non_authority_satisfaction_seal_does_not_advance_state",
    "future_valid_fork_must_satisfy_authority_independently",
    "future_valid_fork_authority_satisfaction_must_target_new_snapshot",
    "private_access_required",
    "network_required_after_clone",
    "media_or_model_payload_present",
    "authority_satisfied",
    "may_advance_now",
    "issued",
    "media_present",
]:
    print(f"{key.upper()}={str(status[key]).lower() if isinstance(status[key], bool) else status[key]}")
PY
