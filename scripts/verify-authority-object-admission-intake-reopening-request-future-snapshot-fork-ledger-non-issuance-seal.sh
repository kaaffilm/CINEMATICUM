#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"

OBJ = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEAL.json")
LAW = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEAL_LAW.json")
STATUS = Path("CASES") / CASE_ID / "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEAL_STATUS.json"
TERMINAL = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_TERMINAL_CLOSURE_SEAL.json")
OUTSIDER = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_OUTSIDER_REPLAY_SEAL.json")
LEDGER = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER.json")

def load(path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

obj = load(OBJ)
law = load(LAW)
status = load(STATUS)
terminal = load(TERMINAL)
outsider = load(OUTSIDER)
ledger = load(LEDGER)

assert ledger["future_snapshot_fork_record_count"] == 0
assert ledger["new_snapshot_record_count"] == 0
assert ledger["future_snapshot_fork_gate_passed_now"] is False
assert ledger["current_snapshot_mutable"] is False

assert outsider["future_snapshot_fork_ledger_outsider_replay_sealed"] is True
assert outsider["outsider_replay_seal_passed_for_current_zero_ledger"] is True
assert outsider["outsider_replay_seal_passed_for_future_fork"] is False

assert terminal["future_snapshot_fork_ledger_terminal_closure_sealed"] is True
assert terminal["terminal_closure_seal_passed_for_current_zero_ledger"] is True
assert terminal["terminal_closure_seal_passed_for_future_fork"] is False
assert terminal["terminal_closure_does_not_issue_motion_picture"] is True
assert terminal["issued"] is False
assert terminal["media_present"] is False

assert obj["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEAL"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEAL_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEAL_STATUS"

for record in (obj, status):
    assert record["case_id"] == CASE_ID
    assert record["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
    assert record["non_issuance_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
    assert record["terminal_closure_scope_preserved"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
    assert record["replay_scope_preserved"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"

    assert record["future_snapshot_fork_ledger_present"] is True
    assert record["future_snapshot_fork_ledger_empty"] is True
    assert record["future_snapshot_fork_ledger_closed_for_current_snapshot"] is True
    assert record["future_snapshot_fork_ledger_terminal_closure_sealed"] is True
    assert record["future_snapshot_fork_ledger_non_issuance_sealed"] is True

    assert record["current_zero_future_snapshot_fork_ledger_terminally_closed"] is True
    assert record["current_zero_future_snapshot_fork_ledger_non_issuing"] is True
    assert record["current_zero_future_snapshot_fork_ledger_not_admissible_motion_picture"] is True
    assert record["current_zero_future_snapshot_fork_ledger_not_release_candidate"] is True
    assert record["current_zero_future_snapshot_fork_ledger_not_media_admission"] is True

    assert record["future_snapshot_fork_gate_passed_now"] is False
    assert record["future_snapshot_fork_gate_open_now"] is False
    assert record["current_snapshot_final"] is True
    assert record["current_snapshot_mutable"] is False
    assert record["current_snapshot_reopenable_by_future_request"] is False
    assert record["current_snapshot_forked_now"] is False

    assert record["future_snapshot_fork_record_count"] == 0
    assert record["valid_future_snapshot_fork_record_count"] == 0
    assert record["invalid_future_snapshot_fork_record_count"] == 0
    assert record["new_snapshot_record_count"] == 0
    assert record["live_reopening_request_count"] == 0
    assert record["valid_reopening_request_count"] == 0
    assert record["accepted_reopening_request_count"] == 0
    assert record["decision_record_count"] == 0
    assert record["enforcement_gate_passed"] is False
    assert record["reopening_gate_open_now"] is False

    assert record["terminal_closure_seal_present"] is True
    assert record["terminal_closure_does_not_issue_motion_picture"] is True
    assert record["terminal_closure_does_not_satisfy_authority"] is True
    assert record["terminal_closure_does_not_advance_state"] is True

    assert record["non_issuance_seal_declared"] is True
    assert record["non_issuance_seal_passed_for_current_zero_ledger"] is True
    assert record["non_issuance_seal_passed_for_future_fork"] is False
    assert record["non_issuance_seal_does_not_reopen_intake"] is True
    assert record["non_issuance_seal_does_not_open_future_fork_gate"] is True
    assert record["non_issuance_seal_does_not_create_future_fork_record"] is True
    assert record["non_issuance_seal_does_not_create_new_snapshot"] is True
    assert record["non_issuance_seal_does_not_reopen_current_snapshot"] is True
    assert record["non_issuance_seal_does_not_mutate_current_snapshot"] is True
    assert record["non_issuance_seal_does_not_mutate_permanent_ledger"] is True
    assert record["non_issuance_seal_does_not_override_terminal_closure"] is True
    assert record["non_issuance_seal_does_not_satisfy_authority"] is True
    assert record["non_issuance_seal_does_not_advance_state"] is True
    assert record["non_issuance_seal_does_not_issue_motion_picture"] is True
    assert record["non_issuance_seal_preserves_zero_media_state"] is True

    assert record["future_valid_fork_must_establish_issuance_independently"] is True
    assert record["future_valid_fork_non_issuance_seal_must_target_new_snapshot"] is True

    assert record["private_access_required"] is False
    assert record["network_required_after_clone"] is False
    assert record["media_or_model_payload_present"] is False
    assert record["raw_media_in_git"] is False
    assert record["model_weights_in_git"] is False
    assert record["release_candidate_ready"] is False
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["issued"] is False
    assert record["media_present"] is False
    assert record["media_admitted"] is False
    assert record["generation_admitted"] is False
    assert record["engine_admitted"] is False

assert law["law_declared"] is True
assert law["current_zero_ledger_terminal_closure_does_not_issue_motion_picture"] is True
assert law["current_zero_ledger_non_issuance_must_be_explicit"] is True
assert law["current_zero_ledger_may_be_reclassified_as_issued"] is False
assert law["current_zero_ledger_may_be_reclassified_as_release_candidate"] is False
assert law["current_zero_ledger_may_admit_media"] is False
assert law["non_issuance_seal_may_open_future_fork_gate_now"] is False
assert law["non_issuance_seal_may_create_future_fork_record_now"] is False
assert law["non_issuance_seal_may_create_new_snapshot_now"] is False
assert law["non_issuance_seal_may_reopen_current_snapshot"] is False
assert law["non_issuance_seal_may_mutate_current_snapshot"] is False
assert law["non_issuance_seal_may_mutate_permanent_ledger"] is False
assert law["non_issuance_seal_may_override_terminal_closure"] is False
assert law["non_issuance_seal_may_satisfy_authority"] is False
assert law["non_issuance_seal_may_advance_state"] is False
assert law["non_issuance_seal_may_issue_motion_picture"] is False
assert law["future_valid_forks_require_independent_issuance_authority"] is True
assert law["future_valid_fork_non_issuance_targets_new_snapshot_only"] is True

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER NON-ISSUANCE SEAL: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"NON_ISSUANCE_SCOPE={obj['non_issuance_scope']}")
print(f"TERMINAL_CLOSURE_SCOPE_PRESERVED={obj['terminal_closure_scope_preserved']}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_PRESENT={str(obj['future_snapshot_fork_ledger_present']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_TERMINAL_CLOSURE_SEALED={str(obj['future_snapshot_fork_ledger_terminal_closure_sealed']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEALED={str(obj['future_snapshot_fork_ledger_non_issuance_sealed']).lower()}")
print(f"CURRENT_ZERO_LEDGER_NON_ISSUING={str(obj['current_zero_future_snapshot_fork_ledger_non_issuing']).lower()}")
print(f"CURRENT_ZERO_LEDGER_NOT_ADMISSIBLE_MOTION_PICTURE={str(obj['current_zero_future_snapshot_fork_ledger_not_admissible_motion_picture']).lower()}")
print(f"CURRENT_ZERO_LEDGER_NOT_RELEASE_CANDIDATE={str(obj['current_zero_future_snapshot_fork_ledger_not_release_candidate']).lower()}")
print(f"CURRENT_ZERO_LEDGER_NOT_MEDIA_ADMISSION={str(obj['current_zero_future_snapshot_fork_ledger_not_media_admission']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_PASSED_NOW={str(obj['future_snapshot_fork_gate_passed_now']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW={str(obj['future_snapshot_fork_gate_open_now']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_RECORD_COUNT={obj['future_snapshot_fork_record_count']}")
print(f"NEW_SNAPSHOT_RECORD_COUNT={obj['new_snapshot_record_count']}")
print(f"TERMINAL_CLOSURE_DOES_NOT_ISSUE_MOTION_PICTURE={str(obj['terminal_closure_does_not_issue_motion_picture']).lower()}")
print(f"NON_ISSUANCE_SEAL_PASSED_FOR_CURRENT_ZERO_LEDGER={str(obj['non_issuance_seal_passed_for_current_zero_ledger']).lower()}")
print(f"NON_ISSUANCE_SEAL_PASSED_FOR_FUTURE_FORK={str(obj['non_issuance_seal_passed_for_future_fork']).lower()}")
print(f"NON_ISSUANCE_SEAL_DOES_NOT_OPEN_FUTURE_FORK_GATE={str(obj['non_issuance_seal_does_not_open_future_fork_gate']).lower()}")
print(f"NON_ISSUANCE_SEAL_DOES_NOT_CREATE_NEW_SNAPSHOT={str(obj['non_issuance_seal_does_not_create_new_snapshot']).lower()}")
print(f"NON_ISSUANCE_SEAL_DOES_NOT_MUTATE_CURRENT_SNAPSHOT={str(obj['non_issuance_seal_does_not_mutate_current_snapshot']).lower()}")
print(f"NON_ISSUANCE_SEAL_DOES_NOT_ISSUE_MOTION_PICTURE={str(obj['non_issuance_seal_does_not_issue_motion_picture']).lower()}")
print(f"FUTURE_VALID_FORK_MUST_ESTABLISH_ISSUANCE_INDEPENDENTLY={str(obj['future_valid_fork_must_establish_issuance_independently']).lower()}")
print(f"PRIVATE_ACCESS_REQUIRED={str(obj['private_access_required']).lower()}")
print(f"NETWORK_REQUIRED_AFTER_CLONE={str(obj['network_required_after_clone']).lower()}")
print(f"MEDIA_OR_MODEL_PAYLOAD_PRESENT={str(obj['media_or_model_payload_present']).lower()}")
print(f"AUTHORITY_SATISFIED={str(obj['authority_satisfied']).lower()}")
print(f"MAY_ADVANCE_NOW={str(obj['may_advance_now']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
PY
