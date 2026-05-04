#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"

OBJ = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER.json")
LAW = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_LAW.json")
STATUS = Path("CASES") / CASE_ID / "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_STATUS.json"
GATE = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_GATE.json")

def load(path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(path.read_text())

obj = load(OBJ)
law = load(LAW)
status = load(STATUS)
gate = load(GATE)

assert gate["fork_scope"] == "FUTURE_VALID_REOPENING_REQUESTS_CREATE_NEW_SNAPSHOT_ONLY"
assert gate["future_snapshot_fork_gate_passed"] is False
assert gate["current_snapshot_final"] is True
assert gate["current_snapshot_mutable"] is False
assert gate["current_snapshot_reopenable_by_future_request"] is False
assert gate["future_valid_reopening_requests_create_new_snapshot"] is True
assert gate["future_valid_reopening_requests_fork_from_current_snapshot"] is True
assert gate["future_valid_reopening_requests_do_not_mutate_current_snapshot"] is True
assert gate["future_valid_reopening_requests_do_not_reopen_current_snapshot"] is True
assert gate["future_snapshot_fork_gate_does_not_reopen_intake"] is True
assert gate["authority_satisfied"] is False
assert gate["may_advance_now"] is False

assert obj["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_STATUS"

for record in (obj, status):
    assert record["case_id"] == CASE_ID
    assert record["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
    assert record["ledger_scope"] == "FUTURE_VALID_REOPENING_REQUEST_SNAPSHOT_FORKS_ONLY"
    assert record["future_snapshot_fork_gate_required"] is True
    assert record["future_snapshot_fork_gate_present"] is True
    assert record["future_snapshot_fork_gate_passed_now"] is False
    assert record["current_snapshot_final"] is True
    assert record["current_snapshot_mutable"] is False
    assert record["current_snapshot_reopenable_by_future_request"] is False
    assert record["current_snapshot_forked_now"] is False
    assert record["current_snapshot_fork_record_count"] == 0
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
    assert record["future_snapshot_fork_ledger_empty"] is True
    assert record["future_snapshot_fork_ledger_closed_for_current_snapshot"] is True
    assert record["future_snapshot_fork_records_require_explicit_reopening_request"] is True
    assert record["future_snapshot_fork_records_require_valid_reopening_request"] is True
    assert record["future_snapshot_fork_records_require_accepted_decision"] is True
    assert record["future_snapshot_fork_records_require_enforcement_gate"] is True
    assert record["future_snapshot_fork_records_create_new_snapshot"] is True
    assert record["future_snapshot_fork_records_do_not_mutate_current_snapshot"] is True
    assert record["future_snapshot_fork_records_do_not_reopen_current_snapshot"] is True
    assert record["future_snapshot_fork_records_do_not_satisfy_current_authority"] is True
    assert record["future_snapshot_fork_records_do_not_advance_current_state"] is True
    assert record["silent_snapshot_fork_forbidden"] is True
    assert record["implicit_snapshot_fork_forbidden"] is True
    assert record["silent_snapshot_mutation_forbidden"] is True
    assert record["ledger_entry_can_reopen_current_snapshot"] is False
    assert record["ledger_entry_can_satisfy_authority"] is False
    assert record["ledger_entry_can_advance_state"] is False
    assert record["ledger_entry_can_issue_motion_picture"] is False
    assert record["future_snapshot_fork_ledger_does_not_reopen_intake"] is True
    assert record["future_snapshot_fork_ledger_does_not_mutate_current_snapshot"] is True
    assert record["future_snapshot_fork_ledger_does_not_satisfy_authority"] is True
    assert record["future_snapshot_fork_ledger_does_not_advance_state"] is True
    assert record["future_snapshot_fork_ledger_does_not_issue_motion_picture"] is True
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["issued"] is False
    assert record["media_present"] is False

assert law["ledger_scope"] == "FUTURE_VALID_REOPENING_REQUEST_SNAPSHOT_FORKS_ONLY"
assert law["future_snapshot_fork_ledger_requires_future_snapshot_fork_gate"] is True
assert law["current_snapshot_final"] is True
assert law["current_snapshot_mutation_forbidden"] is True
assert law["current_snapshot_reopening_by_future_fork_forbidden"] is True
assert law["future_snapshot_fork_records_require_explicit_reopening_request"] is True
assert law["future_snapshot_fork_records_require_valid_reopening_request"] is True
assert law["future_snapshot_fork_records_require_accepted_decision"] is True
assert law["future_snapshot_fork_records_require_enforcement_gate"] is True
assert law["future_snapshot_fork_records_create_new_snapshot"] is True
assert law["future_snapshot_fork_records_do_not_mutate_current_snapshot"] is True
assert law["future_snapshot_fork_records_do_not_reopen_current_snapshot"] is True
assert law["future_snapshot_fork_records_do_not_satisfy_current_authority"] is True
assert law["future_snapshot_fork_records_do_not_advance_current_state"] is True
assert law["silent_snapshot_fork_forbidden"] is True
assert law["implicit_snapshot_fork_forbidden"] is True
assert law["ledger_entry_may_reopen_current_snapshot"] is False
assert law["ledger_entry_may_satisfy_authority"] is False
assert law["ledger_entry_may_advance_state"] is False
assert law["ledger_entry_may_issue_motion_picture"] is False

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"LEDGER_SCOPE={obj['ledger_scope']}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_PRESENT={str(obj['future_snapshot_fork_gate_present']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_PASSED_NOW={str(obj['future_snapshot_fork_gate_passed_now']).lower()}")
print(f"CURRENT_SNAPSHOT_FINAL={str(obj['current_snapshot_final']).lower()}")
print(f"CURRENT_SNAPSHOT_MUTABLE={str(obj['current_snapshot_mutable']).lower()}")
print(f"CURRENT_SNAPSHOT_REOPENABLE_BY_FUTURE_REQUEST={str(obj['current_snapshot_reopenable_by_future_request']).lower()}")
print(f"CURRENT_SNAPSHOT_FORKED_NOW={str(obj['current_snapshot_forked_now']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_RECORD_COUNT={obj['future_snapshot_fork_record_count']}")
print(f"NEW_SNAPSHOT_RECORD_COUNT={obj['new_snapshot_record_count']}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_EMPTY={str(obj['future_snapshot_fork_ledger_empty']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_CLOSED_FOR_CURRENT_SNAPSHOT={str(obj['future_snapshot_fork_ledger_closed_for_current_snapshot']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_RECORDS_CREATE_NEW_SNAPSHOT={str(obj['future_snapshot_fork_records_create_new_snapshot']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_RECORDS_DO_NOT_MUTATE_CURRENT_SNAPSHOT={str(obj['future_snapshot_fork_records_do_not_mutate_current_snapshot']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_RECORDS_DO_NOT_REOPEN_CURRENT_SNAPSHOT={str(obj['future_snapshot_fork_records_do_not_reopen_current_snapshot']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_DOES_NOT_REOPEN_INTAKE={str(obj['future_snapshot_fork_ledger_does_not_reopen_intake']).lower()}")
print(f"AUTHORITY_SATISFIED={str(obj['authority_satisfied']).lower()}")
print(f"MAY_ADVANCE_NOW={str(obj['may_advance_now']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
PY
