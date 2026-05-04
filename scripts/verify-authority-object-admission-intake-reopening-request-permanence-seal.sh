#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"

OBJ = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_PERMANENCE_SEAL.json")
LAW = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_PERMANENCE_SEAL_LAW.json")
STATUS = Path("CASES") / CASE_ID / "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_PERMANENCE_SEAL_STATUS.json"
TERMINAL = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_TERMINAL_SEAL.json")

def load(path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(path.read_text())

obj = load(OBJ)
law = load(LAW)
status = load(STATUS)
terminal = load(TERMINAL)

assert obj["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_PERMANENCE_SEAL"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_PERMANENCE_SEAL_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_PERMANENCE_SEAL_STATUS"

assert terminal["reopening_request_terminally_sealed"] is True
assert terminal["terminal_seal_does_not_reopen_intake"] is True
assert terminal["terminal_seal_does_not_satisfy_authority"] is True
assert terminal["terminal_seal_does_not_advance_state"] is True

assert obj["case_id"] == CASE_ID
assert status["case_id"] == CASE_ID
assert obj["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert status["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

assert obj["permanence_scope"] == "CURRENT_ZERO_REOPENING_REQUEST_SNAPSHOT_ONLY"
assert status["permanence_scope"] == "CURRENT_ZERO_REOPENING_REQUEST_SNAPSHOT_ONLY"
assert law["permanence_scope"] == "CURRENT_ZERO_REOPENING_REQUEST_SNAPSHOT_ONLY"

for record in (obj, status):
    assert record["terminal_seal_required"] is True
    assert record["terminal_seal_present"] is True
    assert record["reopening_request_terminally_sealed"] is True
    assert record["reopening_request_permanence_sealed"] is True
    assert record["current_snapshot_final"] is True
    assert record["current_snapshot_mutable"] is False
    assert record["future_valid_reopening_requests_allowed_under_law"] is True
    assert record["future_valid_reopening_requests_create_new_snapshot"] is True
    assert record["future_valid_reopening_requests_do_not_mutate_current_snapshot"] is True
    assert record["silent_reopening_forbidden"] is True
    assert record["silent_snapshot_mutation_forbidden"] is True
    assert record["live_reopening_request_count"] == 0
    assert record["valid_reopening_request_count"] == 0
    assert record["decision_record_count"] == 0
    assert record["accepted_reopening_request_count"] == 0
    assert record["rejected_reopening_request_count"] == 0
    assert record["all_live_reopening_requests_have_decisions"] is True
    assert record["accepted_reopening_request_present"] is False
    assert record["enforcement_gate_passed"] is False
    assert record["reopening_gate_open_now"] is False
    assert record["no_unadjudicated_reopening_request_records"] is True
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["issued"] is False
    assert record["media_present"] is False

assert obj["permanence_seal_does_not_reopen_intake"] is True
assert obj["permanence_seal_does_not_satisfy_authority"] is True
assert obj["permanence_seal_does_not_advance_state"] is True
assert obj["permanence_seal_does_not_issue_motion_picture"] is True

assert law["permanence_requires_terminal_seal"] is True
assert law["permanence_requires_zero_live_reopening_requests"] is True
assert law["permanence_requires_no_unadjudicated_reopening_request_records"] is True
assert law["current_snapshot_mutation_forbidden"] is True
assert law["future_valid_reopening_requests_allowed_under_law"] is True
assert law["future_valid_reopening_requests_create_new_snapshot"] is True
assert law["future_valid_reopening_requests_do_not_mutate_current_snapshot"] is True
assert law["silent_reopening_forbidden"] is True
assert law["permanence_may_reopen_intake"] is False
assert law["permanence_may_satisfy_authority"] is False
assert law["permanence_may_advance_state"] is False
assert law["permanence_may_issue_motion_picture"] is False

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST PERMANENCE SEAL: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"PERMANENCE_SCOPE={obj['permanence_scope']}")
print(f"REOPENING_REQUEST_TERMINALLY_SEALED={str(obj['reopening_request_terminally_sealed']).lower()}")
print(f"REOPENING_REQUEST_PERMANENCE_SEALED={str(obj['reopening_request_permanence_sealed']).lower()}")
print(f"CURRENT_SNAPSHOT_MUTABLE={str(obj['current_snapshot_mutable']).lower()}")
print(f"FUTURE_VALID_REOPENING_REQUESTS_CREATE_NEW_SNAPSHOT={str(obj['future_valid_reopening_requests_create_new_snapshot']).lower()}")
print(f"FUTURE_VALID_REOPENING_REQUESTS_DO_NOT_MUTATE_CURRENT_SNAPSHOT={str(obj['future_valid_reopening_requests_do_not_mutate_current_snapshot']).lower()}")
print(f"SILENT_SNAPSHOT_MUTATION_FORBIDDEN={str(obj['silent_snapshot_mutation_forbidden']).lower()}")
print(f"LIVE_REOPENING_REQUEST_COUNT={obj['live_reopening_request_count']}")
print(f"VALID_REOPENING_REQUEST_COUNT={obj['valid_reopening_request_count']}")
print(f"DECISION_RECORD_COUNT={obj['decision_record_count']}")
print(f"ENFORCEMENT_GATE_PASSED={str(obj['enforcement_gate_passed']).lower()}")
print(f"REOPENING_GATE_OPEN_NOW={str(obj['reopening_gate_open_now']).lower()}")
print(f"PERMANENCE_SEAL_DOES_NOT_REOPEN_INTAKE={str(obj['permanence_seal_does_not_reopen_intake']).lower()}")
print(f"AUTHORITY_SATISFIED={str(obj['authority_satisfied']).lower()}")
print(f"MAY_ADVANCE_NOW={str(obj['may_advance_now']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
PY
