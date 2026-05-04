#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"

OBJ = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_FINALITY_SEAL.json")
LAW = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_FINALITY_SEAL_LAW.json")
STATUS = Path("CASES") / CASE_ID / "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_FINALITY_SEAL_STATUS.json"
CLOSURE = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_CLOSURE_SEAL.json")
LEDGER = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER.json")

def load(path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(path.read_text())

obj = load(OBJ)
law = load(LAW)
status = load(STATUS)
closure = load(CLOSURE)
ledger = load(LEDGER)

assert ledger["ledger_scope"] == "FUTURE_VALID_REOPENING_REQUEST_SNAPSHOT_FORKS_ONLY"
assert ledger["future_snapshot_fork_gate_present"] is True
assert ledger["future_snapshot_fork_gate_passed_now"] is False
assert ledger["current_snapshot_final"] is True
assert ledger["current_snapshot_mutable"] is False
assert ledger["current_snapshot_reopenable_by_future_request"] is False
assert ledger["current_snapshot_forked_now"] is False
assert ledger["future_snapshot_fork_record_count"] == 0
assert ledger["new_snapshot_record_count"] == 0
assert ledger["future_snapshot_fork_ledger_empty"] is True
assert ledger["future_snapshot_fork_ledger_closed_for_current_snapshot"] is True
assert ledger["future_snapshot_fork_ledger_does_not_reopen_intake"] is True

assert closure["closure_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
assert closure["future_snapshot_fork_ledger_present"] is True
assert closure["future_snapshot_fork_ledger_empty"] is True
assert closure["future_snapshot_fork_ledger_closed_for_current_snapshot"] is True
assert closure["future_snapshot_fork_ledger_closure_sealed"] is True
assert closure["future_snapshot_fork_gate_passed_now"] is False
assert closure["current_snapshot_final"] is True
assert closure["current_snapshot_mutable"] is False
assert closure["current_snapshot_forked_now"] is False
assert closure["future_snapshot_fork_record_count"] == 0
assert closure["new_snapshot_record_count"] == 0
assert closure["no_new_snapshot_created_now"] is True
assert closure["closure_seal_does_not_open_future_fork_gate"] is True
assert closure["closure_seal_does_not_mutate_current_snapshot"] is True
assert closure["authority_satisfied"] is False
assert closure["may_advance_now"] is False

assert obj["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_FINALITY_SEAL"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_FINALITY_SEAL_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_FINALITY_SEAL_STATUS"

for record in (obj, status):
    assert record["case_id"] == CASE_ID
    assert record["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
    assert record["finality_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
    assert record["future_snapshot_fork_ledger_present"] is True
    assert record["future_snapshot_fork_ledger_empty"] is True
    assert record["future_snapshot_fork_ledger_closed_for_current_snapshot"] is True
    assert record["future_snapshot_fork_ledger_closure_seal_present"] is True
    assert record["future_snapshot_fork_ledger_closure_sealed"] is True
    assert record["future_snapshot_fork_ledger_finality_sealed"] is True
    assert record["current_zero_future_snapshot_fork_ledger_final"] is True
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
    assert record["no_current_snapshot_fork_records"] is True
    assert record["no_future_snapshot_fork_records"] is True
    assert record["no_new_snapshot_created_now"] is True
    assert record["no_unfinalized_fork_records"] is True
    assert record["no_unadjudicated_fork_records"] is True
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
    assert record["finality_seal_can_reopen_current_snapshot"] is False
    assert record["finality_seal_can_create_new_snapshot"] is False
    assert record["finality_seal_can_open_future_fork_gate"] is False
    assert record["finality_seal_can_satisfy_authority"] is False
    assert record["finality_seal_can_advance_state"] is False
    assert record["finality_seal_can_issue_motion_picture"] is False
    assert record["finality_seal_does_not_reopen_intake"] is True
    assert record["finality_seal_does_not_open_future_fork_gate"] is True
    assert record["finality_seal_does_not_create_new_snapshot"] is True
    assert record["finality_seal_does_not_mutate_current_snapshot"] is True
    assert record["finality_seal_does_not_reopen_current_snapshot"] is True
    assert record["finality_seal_does_not_satisfy_authority"] is True
    assert record["finality_seal_does_not_advance_state"] is True
    assert record["finality_seal_does_not_issue_motion_picture"] is True
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["issued"] is False
    assert record["media_present"] is False

assert law["finality_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
assert law["future_snapshot_fork_ledger_required"] is True
assert law["future_snapshot_fork_ledger_closure_seal_required"] is True
assert law["future_snapshot_fork_ledger_must_be_empty_for_current_snapshot"] is True
assert law["future_snapshot_fork_ledger_must_be_closed_for_current_snapshot"] is True
assert law["future_snapshot_fork_ledger_must_be_final_for_current_snapshot"] is True
assert law["current_snapshot_final"] is True
assert law["current_snapshot_mutation_forbidden"] is True
assert law["current_snapshot_reopening_by_future_fork_forbidden"] is True
assert law["finality_seal_may_open_future_fork_gate"] is False
assert law["finality_seal_may_create_new_snapshot"] is False
assert law["finality_seal_may_reopen_current_snapshot"] is False
assert law["finality_seal_may_satisfy_authority"] is False
assert law["finality_seal_may_advance_state"] is False
assert law["finality_seal_may_issue_motion_picture"] is False
assert law["future_snapshot_fork_records_require_explicit_reopening_request"] is True
assert law["future_snapshot_fork_records_require_valid_reopening_request"] is True
assert law["future_snapshot_fork_records_require_accepted_decision"] is True
assert law["future_snapshot_fork_records_require_enforcement_gate"] is True
assert law["future_snapshot_fork_records_create_new_snapshot"] is True
assert law["future_snapshot_fork_records_do_not_mutate_current_snapshot"] is True
assert law["future_snapshot_fork_records_do_not_reopen_current_snapshot"] is True
assert law["silent_snapshot_fork_forbidden"] is True
assert law["implicit_snapshot_fork_forbidden"] is True
assert law["silent_snapshot_mutation_forbidden"] is True

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER FINALITY SEAL: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"FINALITY_SCOPE={obj['finality_scope']}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_PRESENT={str(obj['future_snapshot_fork_ledger_present']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_EMPTY={str(obj['future_snapshot_fork_ledger_empty']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_CLOSED_FOR_CURRENT_SNAPSHOT={str(obj['future_snapshot_fork_ledger_closed_for_current_snapshot']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_CLOSURE_SEAL_PRESENT={str(obj['future_snapshot_fork_ledger_closure_seal_present']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_CLOSURE_SEALED={str(obj['future_snapshot_fork_ledger_closure_sealed']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_FINALITY_SEALED={str(obj['future_snapshot_fork_ledger_finality_sealed']).lower()}")
print(f"CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_FINAL={str(obj['current_zero_future_snapshot_fork_ledger_final']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_PASSED_NOW={str(obj['future_snapshot_fork_gate_passed_now']).lower()}")
print(f"CURRENT_SNAPSHOT_FINAL={str(obj['current_snapshot_final']).lower()}")
print(f"CURRENT_SNAPSHOT_MUTABLE={str(obj['current_snapshot_mutable']).lower()}")
print(f"CURRENT_SNAPSHOT_FORKED_NOW={str(obj['current_snapshot_forked_now']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_RECORD_COUNT={obj['future_snapshot_fork_record_count']}")
print(f"NEW_SNAPSHOT_RECORD_COUNT={obj['new_snapshot_record_count']}")
print(f"NO_UNFINALIZED_FORK_RECORDS={str(obj['no_unfinalized_fork_records']).lower()}")
print(f"NO_UNADJUDICATED_FORK_RECORDS={str(obj['no_unadjudicated_fork_records']).lower()}")
print(f"FINALITY_SEAL_DOES_NOT_REOPEN_INTAKE={str(obj['finality_seal_does_not_reopen_intake']).lower()}")
print(f"FINALITY_SEAL_DOES_NOT_OPEN_FUTURE_FORK_GATE={str(obj['finality_seal_does_not_open_future_fork_gate']).lower()}")
print(f"FINALITY_SEAL_DOES_NOT_CREATE_NEW_SNAPSHOT={str(obj['finality_seal_does_not_create_new_snapshot']).lower()}")
print(f"FINALITY_SEAL_DOES_NOT_MUTATE_CURRENT_SNAPSHOT={str(obj['finality_seal_does_not_mutate_current_snapshot']).lower()}")
print(f"AUTHORITY_SATISFIED={str(obj['authority_satisfied']).lower()}")
print(f"MAY_ADVANCE_NOW={str(obj['may_advance_now']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
PY
