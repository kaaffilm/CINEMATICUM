#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"

OBJ = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_OUTSIDER_REPLAY_SEAL.json")
LAW = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_OUTSIDER_REPLAY_SEAL_LAW.json")
STATUS = Path("CASES") / CASE_ID / "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_OUTSIDER_REPLAY_SEAL_STATUS.json"
FUTURE_CONTINUITY = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_FUTURE_CONTINUITY_SEAL.json")
PERMANENCE = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_PERMANENCE_SEAL.json")
LEDGER = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER.json")

def load(path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(path.read_text())

obj = load(OBJ)
law = load(LAW)
status = load(STATUS)
future_continuity = load(FUTURE_CONTINUITY)
permanence = load(PERMANENCE)
ledger = load(LEDGER)

assert ledger["future_snapshot_fork_ledger_empty"] is True
assert ledger["future_snapshot_fork_ledger_closed_for_current_snapshot"] is True
assert ledger["future_snapshot_fork_gate_passed_now"] is False
assert ledger["current_snapshot_final"] is True
assert ledger["current_snapshot_mutable"] is False
assert ledger["future_snapshot_fork_record_count"] == 0
assert ledger["new_snapshot_record_count"] == 0

assert permanence["future_snapshot_fork_ledger_permanence_sealed"] is True
assert permanence["current_zero_future_snapshot_fork_ledger_permanent"] is True
assert permanence["current_zero_future_snapshot_fork_ledger_mutable"] is False

assert future_continuity["future_snapshot_fork_ledger_future_continuity_sealed"] is True
assert future_continuity["future_continuity_seal_preserves_permanence"] is True
assert future_continuity["future_continuity_seal_routes_future_valid_forks_to_new_snapshot"] is True
assert future_continuity["future_continuity_seal_does_not_create_new_snapshot_now"] is True
assert future_continuity["future_continuity_seal_does_not_mutate_permanent_ledger"] is True

assert obj["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_OUTSIDER_REPLAY_SEAL"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_OUTSIDER_REPLAY_SEAL_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_OUTSIDER_REPLAY_SEAL_STATUS"

for record in (obj, status):
    assert record["case_id"] == CASE_ID
    assert record["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
    assert record["replay_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
    assert record["continuity_scope_preserved"] == "FUTURE_VALID_REOPENING_REQUEST_SNAPSHOT_FORKS_ONLY"
    assert record["permanence_scope_preserved"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"

    assert record["future_snapshot_fork_ledger_present"] is True
    assert record["future_snapshot_fork_ledger_empty"] is True
    assert record["future_snapshot_fork_ledger_closed_for_current_snapshot"] is True
    assert record["future_snapshot_fork_ledger_closure_sealed"] is True
    assert record["future_snapshot_fork_ledger_finality_sealed"] is True
    assert record["future_snapshot_fork_ledger_terminally_sealed"] is True
    assert record["future_snapshot_fork_ledger_permanence_sealed"] is True
    assert record["future_snapshot_fork_ledger_future_continuity_sealed"] is True
    assert record["future_snapshot_fork_ledger_outsider_replay_sealed"] is True

    assert record["future_continuity_seal_present"] is True
    assert record["future_continuity_seal_preserves_permanence"] is True
    assert record["future_continuity_seal_routes_future_valid_forks_to_new_snapshot"] is True

    assert record["current_zero_future_snapshot_fork_ledger_final"] is True
    assert record["current_zero_future_snapshot_fork_ledger_terminal"] is True
    assert record["current_zero_future_snapshot_fork_ledger_permanent"] is True
    assert record["current_zero_future_snapshot_fork_ledger_mutable"] is False
    assert record["current_zero_future_snapshot_fork_ledger_replayable_without_future_fork_records"] is True
    assert record["current_zero_future_snapshot_fork_ledger_replay_requires_private_access"] is False
    assert record["current_zero_future_snapshot_fork_ledger_replay_requires_network"] is False
    assert record["current_zero_future_snapshot_fork_ledger_replay_requires_media_payload"] is False
    assert record["current_zero_future_snapshot_fork_ledger_replay_requires_model_weights"] is False

    assert record["future_snapshot_fork_gate_present"] is True
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

    assert record["outsider_replay_seal_passed_for_current_zero_ledger"] is True
    assert record["outsider_replay_seal_passed_for_future_fork"] is False
    assert record["outsider_replay_seal_passed_for_new_snapshot"] is False
    assert record["outsider_replay_artifact_required_for_future_fork"] is True
    assert record["outsider_replay_artifact_present_for_future_fork"] is False
    assert record["outsider_replay_does_not_create_future_fork_record"] is True
    assert record["outsider_replay_does_not_create_new_snapshot"] is True
    assert record["outsider_replay_does_not_open_future_fork_gate"] is True
    assert record["outsider_replay_does_not_reopen_current_snapshot"] is True
    assert record["outsider_replay_does_not_mutate_current_snapshot"] is True
    assert record["outsider_replay_does_not_mutate_permanent_ledger"] is True
    assert record["outsider_replay_does_not_satisfy_authority"] is True
    assert record["outsider_replay_does_not_advance_state"] is True
    assert record["outsider_replay_does_not_issue_motion_picture"] is True

    assert record["future_valid_reopening_requests_allowed_under_law"] is True
    assert record["future_valid_reopening_requests_require_explicit_request"] is True
    assert record["future_valid_reopening_requests_require_validation"] is True
    assert record["future_valid_reopening_requests_require_decision"] is True
    assert record["future_valid_reopening_requests_require_enforcement_gate"] is True
    assert record["future_valid_reopening_requests_create_new_snapshot"] is True
    assert record["future_valid_reopening_requests_do_not_mutate_current_snapshot"] is True
    assert record["future_valid_reopening_requests_do_not_mutate_permanent_fork_ledger"] is True
    assert record["future_valid_fork_outsider_replay_must_target_new_snapshot"] is True
    assert record["future_valid_fork_outsider_replay_must_not_replay_as_current_snapshot"] is True

    assert record["private_access_required"] is False
    assert record["network_required_after_clone"] is False
    assert record["media_or_model_payload_present"] is False
    assert record["raw_media_in_git"] is False
    assert record["model_weights_in_git"] is False
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["issued"] is False
    assert record["media_present"] is False

assert law["replay_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
assert law["future_continuity_seal_required"] is True
assert law["future_snapshot_fork_ledger_required"] is True
assert law["future_snapshot_fork_ledger_must_be_permanent"] is True
assert law["future_snapshot_fork_ledger_must_be_future_continuity_sealed"] is True
assert law["current_zero_ledger_must_replay_without_future_records"] is True
assert law["current_zero_ledger_must_replay_without_private_access"] is True
assert law["current_zero_ledger_must_replay_without_network"] is True
assert law["current_zero_ledger_must_replay_without_media_payload"] is True
assert law["current_zero_ledger_must_replay_without_model_weights"] is True
assert law["outsider_replay_may_open_future_fork_gate_now"] is False
assert law["outsider_replay_may_create_new_snapshot_now"] is False
assert law["outsider_replay_may_reopen_current_snapshot"] is False
assert law["outsider_replay_may_mutate_current_snapshot"] is False
assert law["outsider_replay_may_mutate_permanent_ledger"] is False
assert law["outsider_replay_may_satisfy_authority"] is False
assert law["outsider_replay_may_advance_state"] is False
assert law["outsider_replay_may_issue_motion_picture"] is False
assert law["future_valid_forks_require_their_own_outsider_replay_artifact"] is True
assert law["future_valid_fork_outsider_replay_targets_new_snapshot_only"] is True
assert law["future_valid_fork_outsider_replay_does_not_reclassify_current_zero_ledger"] is True

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER OUTSIDER REPLAY SEAL: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"REPLAY_SCOPE={obj['replay_scope']}")
print(f"CONTINUITY_SCOPE_PRESERVED={obj['continuity_scope_preserved']}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_PRESENT={str(obj['future_snapshot_fork_ledger_present']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_FUTURE_CONTINUITY_SEALED={str(obj['future_snapshot_fork_ledger_future_continuity_sealed']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_OUTSIDER_REPLAY_SEALED={str(obj['future_snapshot_fork_ledger_outsider_replay_sealed']).lower()}")
print(f"CURRENT_ZERO_LEDGER_REPLAYABLE_WITHOUT_FUTURE_FORK_RECORDS={str(obj['current_zero_future_snapshot_fork_ledger_replayable_without_future_fork_records']).lower()}")
print(f"CURRENT_ZERO_LEDGER_REPLAY_REQUIRES_PRIVATE_ACCESS={str(obj['current_zero_future_snapshot_fork_ledger_replay_requires_private_access']).lower()}")
print(f"CURRENT_ZERO_LEDGER_REPLAY_REQUIRES_NETWORK={str(obj['current_zero_future_snapshot_fork_ledger_replay_requires_network']).lower()}")
print(f"CURRENT_ZERO_LEDGER_REPLAY_REQUIRES_MEDIA_PAYLOAD={str(obj['current_zero_future_snapshot_fork_ledger_replay_requires_media_payload']).lower()}")
print(f"CURRENT_ZERO_LEDGER_REPLAY_REQUIRES_MODEL_WEIGHTS={str(obj['current_zero_future_snapshot_fork_ledger_replay_requires_model_weights']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_PASSED_NOW={str(obj['future_snapshot_fork_gate_passed_now']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW={str(obj['future_snapshot_fork_gate_open_now']).lower()}")
print(f"CURRENT_SNAPSHOT_FINAL={str(obj['current_snapshot_final']).lower()}")
print(f"CURRENT_SNAPSHOT_MUTABLE={str(obj['current_snapshot_mutable']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_RECORD_COUNT={obj['future_snapshot_fork_record_count']}")
print(f"NEW_SNAPSHOT_RECORD_COUNT={obj['new_snapshot_record_count']}")
print(f"OUTSIDER_REPLAY_SEAL_PASSED_FOR_CURRENT_ZERO_LEDGER={str(obj['outsider_replay_seal_passed_for_current_zero_ledger']).lower()}")
print(f"OUTSIDER_REPLAY_SEAL_PASSED_FOR_FUTURE_FORK={str(obj['outsider_replay_seal_passed_for_future_fork']).lower()}")
print(f"OUTSIDER_REPLAY_ARTIFACT_REQUIRED_FOR_FUTURE_FORK={str(obj['outsider_replay_artifact_required_for_future_fork']).lower()}")
print(f"OUTSIDER_REPLAY_ARTIFACT_PRESENT_FOR_FUTURE_FORK={str(obj['outsider_replay_artifact_present_for_future_fork']).lower()}")
print(f"OUTSIDER_REPLAY_DOES_NOT_OPEN_FUTURE_FORK_GATE={str(obj['outsider_replay_does_not_open_future_fork_gate']).lower()}")
print(f"OUTSIDER_REPLAY_DOES_NOT_CREATE_NEW_SNAPSHOT={str(obj['outsider_replay_does_not_create_new_snapshot']).lower()}")
print(f"OUTSIDER_REPLAY_DOES_NOT_MUTATE_CURRENT_SNAPSHOT={str(obj['outsider_replay_does_not_mutate_current_snapshot']).lower()}")
print(f"OUTSIDER_REPLAY_DOES_NOT_MUTATE_PERMANENT_LEDGER={str(obj['outsider_replay_does_not_mutate_permanent_ledger']).lower()}")
print(f"FUTURE_VALID_FORK_OUTSIDER_REPLAY_MUST_TARGET_NEW_SNAPSHOT={str(obj['future_valid_fork_outsider_replay_must_target_new_snapshot']).lower()}")
print(f"PRIVATE_ACCESS_REQUIRED={str(obj['private_access_required']).lower()}")
print(f"NETWORK_REQUIRED_AFTER_CLONE={str(obj['network_required_after_clone']).lower()}")
print(f"MEDIA_OR_MODEL_PAYLOAD_PRESENT={str(obj['media_or_model_payload_present']).lower()}")
print(f"AUTHORITY_SATISFIED={str(obj['authority_satisfied']).lower()}")
print(f"MAY_ADVANCE_NOW={str(obj['may_advance_now']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
PY
