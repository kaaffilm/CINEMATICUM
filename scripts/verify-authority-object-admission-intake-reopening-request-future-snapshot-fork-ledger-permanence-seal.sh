#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"

OBJ = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_PERMANENCE_SEAL.json")
LAW = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_PERMANENCE_SEAL_LAW.json")
STATUS = Path("CASES") / CASE_ID / "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_PERMANENCE_SEAL_STATUS.json"
TERMINAL = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_TERMINAL_SEAL.json")
FINALITY = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_FINALITY_SEAL.json")
CLOSURE = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_CLOSURE_SEAL.json")
LEDGER = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER.json")

def load(path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(path.read_text())

obj = load(OBJ)
law = load(LAW)
status = load(STATUS)
terminal = load(TERMINAL)
finality = load(FINALITY)
closure = load(CLOSURE)
ledger = load(LEDGER)

assert ledger["future_snapshot_fork_gate_passed_now"] is False
assert ledger["current_snapshot_final"] is True
assert ledger["current_snapshot_mutable"] is False
assert ledger["current_snapshot_reopenable_by_future_request"] is False
assert ledger["current_snapshot_forked_now"] is False
assert ledger["future_snapshot_fork_record_count"] == 0
assert ledger["new_snapshot_record_count"] == 0
assert ledger["future_snapshot_fork_ledger_empty"] is True
assert ledger["future_snapshot_fork_ledger_closed_for_current_snapshot"] is True

assert closure["future_snapshot_fork_ledger_closure_sealed"] is True
assert closure["future_snapshot_fork_gate_passed_now"] is False
assert closure["current_snapshot_mutable"] is False
assert closure["current_snapshot_forked_now"] is False

assert finality["future_snapshot_fork_ledger_finality_sealed"] is True
assert finality["current_zero_future_snapshot_fork_ledger_final"] is True
assert finality["future_snapshot_fork_gate_passed_now"] is False
assert finality["current_snapshot_mutable"] is False
assert finality["current_snapshot_forked_now"] is False
assert finality["future_snapshot_fork_record_count"] == 0
assert finality["new_snapshot_record_count"] == 0
assert finality["finality_seal_does_not_open_future_fork_gate"] is True
assert finality["finality_seal_does_not_create_new_snapshot"] is True
assert finality["finality_seal_does_not_mutate_current_snapshot"] is True

assert terminal["terminal_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
assert terminal["future_snapshot_fork_ledger_terminally_sealed"] is True
assert terminal["current_zero_future_snapshot_fork_ledger_terminal"] is True
assert terminal["future_snapshot_fork_gate_passed_now"] is False
assert terminal["current_snapshot_mutable"] is False
assert terminal["current_snapshot_forked_now"] is False
assert terminal["future_snapshot_fork_record_count"] == 0
assert terminal["new_snapshot_record_count"] == 0
assert terminal["no_unfinalized_fork_records"] is True
assert terminal["no_unadjudicated_fork_records"] is True
assert terminal["no_unterminalized_fork_records"] is True
assert terminal["terminal_seal_does_not_open_future_fork_gate"] is True
assert terminal["terminal_seal_does_not_create_new_snapshot"] is True
assert terminal["terminal_seal_does_not_mutate_current_snapshot"] is True
assert terminal["authority_satisfied"] is False
assert terminal["may_advance_now"] is False

assert obj["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_PERMANENCE_SEAL"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_PERMANENCE_SEAL_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_PERMANENCE_SEAL_STATUS"

for record in (obj, status):
    assert record["case_id"] == CASE_ID
    assert record["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
    assert record["permanence_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
    assert record["future_snapshot_fork_ledger_present"] is True
    assert record["future_snapshot_fork_ledger_empty"] is True
    assert record["future_snapshot_fork_ledger_closed_for_current_snapshot"] is True
    assert record["future_snapshot_fork_ledger_closure_seal_present"] is True
    assert record["future_snapshot_fork_ledger_closure_sealed"] is True
    assert record["future_snapshot_fork_ledger_finality_seal_present"] is True
    assert record["future_snapshot_fork_ledger_finality_sealed"] is True
    assert record["future_snapshot_fork_ledger_terminal_seal_present"] is True
    assert record["future_snapshot_fork_ledger_terminally_sealed"] is True
    assert record["future_snapshot_fork_ledger_permanence_sealed"] is True
    assert record["current_zero_future_snapshot_fork_ledger_final"] is True
    assert record["current_zero_future_snapshot_fork_ledger_terminal"] is True
    assert record["current_zero_future_snapshot_fork_ledger_permanent"] is True
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
    assert record["no_unterminalized_fork_records"] is True
    assert record["no_unpermanent_fork_records"] is True
    assert record["future_valid_reopening_requests_allowed_under_law"] is True
    assert record["future_valid_reopening_requests_require_explicit_request"] is True
    assert record["future_valid_reopening_requests_require_validation"] is True
    assert record["future_valid_reopening_requests_require_decision"] is True
    assert record["future_valid_reopening_requests_require_enforcement_gate"] is True
    assert record["future_valid_reopening_requests_create_new_snapshot"] is True
    assert record["future_valid_reopening_requests_fork_from_current_snapshot"] is True
    assert record["future_valid_reopening_requests_do_not_mutate_current_snapshot"] is True
    assert record["future_valid_reopening_requests_do_not_reopen_current_snapshot"] is True
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
    assert record["current_zero_future_snapshot_fork_ledger_mutable"] is False
    assert record["current_zero_future_snapshot_fork_ledger_reopenable"] is False
    assert record["current_zero_future_snapshot_fork_ledger_reissuable"] is False
    assert record["permanence_seal_can_reopen_current_snapshot"] is False
    assert record["permanence_seal_can_create_new_snapshot"] is False
    assert record["permanence_seal_can_open_future_fork_gate"] is False
    assert record["permanence_seal_can_satisfy_authority"] is False
    assert record["permanence_seal_can_advance_state"] is False
    assert record["permanence_seal_can_issue_motion_picture"] is False
    assert record["permanence_seal_does_not_reopen_intake"] is True
    assert record["permanence_seal_does_not_open_future_fork_gate"] is True
    assert record["permanence_seal_does_not_create_new_snapshot"] is True
    assert record["permanence_seal_does_not_mutate_current_snapshot"] is True
    assert record["permanence_seal_does_not_reopen_current_snapshot"] is True
    assert record["permanence_seal_does_not_mutate_terminal_ledger"] is True
    assert record["permanence_seal_does_not_satisfy_authority"] is True
    assert record["permanence_seal_does_not_advance_state"] is True
    assert record["permanence_seal_does_not_issue_motion_picture"] is True
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["issued"] is False
    assert record["media_present"] is False

assert law["permanence_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
assert law["future_snapshot_fork_ledger_required"] is True
assert law["future_snapshot_fork_ledger_closure_seal_required"] is True
assert law["future_snapshot_fork_ledger_finality_seal_required"] is True
assert law["future_snapshot_fork_ledger_terminal_seal_required"] is True
assert law["future_snapshot_fork_ledger_must_be_empty_for_current_snapshot"] is True
assert law["future_snapshot_fork_ledger_must_be_closed_for_current_snapshot"] is True
assert law["future_snapshot_fork_ledger_must_be_final_for_current_snapshot"] is True
assert law["future_snapshot_fork_ledger_must_be_terminal_for_current_snapshot"] is True
assert law["future_snapshot_fork_ledger_must_be_permanent_for_current_snapshot"] is True
assert law["current_snapshot_final"] is True
assert law["current_snapshot_mutation_forbidden"] is True
assert law["current_snapshot_reopening_by_future_fork_forbidden"] is True
assert law["current_zero_future_snapshot_fork_ledger_mutation_forbidden"] is True
assert law["current_zero_future_snapshot_fork_ledger_reopening_forbidden"] is True
assert law["permanence_seal_may_open_future_fork_gate"] is False
assert law["permanence_seal_may_create_new_snapshot"] is False
assert law["permanence_seal_may_reopen_current_snapshot"] is False
assert law["permanence_seal_may_satisfy_authority"] is False
assert law["permanence_seal_may_advance_state"] is False
assert law["permanence_seal_may_issue_motion_picture"] is False
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

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER PERMANENCE SEAL: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"PERMANENCE_SCOPE={obj['permanence_scope']}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_PRESENT={str(obj['future_snapshot_fork_ledger_present']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_EMPTY={str(obj['future_snapshot_fork_ledger_empty']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_CLOSED_FOR_CURRENT_SNAPSHOT={str(obj['future_snapshot_fork_ledger_closed_for_current_snapshot']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_TERMINAL_SEAL_PRESENT={str(obj['future_snapshot_fork_ledger_terminal_seal_present']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_TERMINALLY_SEALED={str(obj['future_snapshot_fork_ledger_terminally_sealed']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_LEDGER_PERMANENCE_SEALED={str(obj['future_snapshot_fork_ledger_permanence_sealed']).lower()}")
print(f"CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_PERMANENT={str(obj['current_zero_future_snapshot_fork_ledger_permanent']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_PASSED_NOW={str(obj['future_snapshot_fork_gate_passed_now']).lower()}")
print(f"CURRENT_SNAPSHOT_FINAL={str(obj['current_snapshot_final']).lower()}")
print(f"CURRENT_SNAPSHOT_MUTABLE={str(obj['current_snapshot_mutable']).lower()}")
print(f"CURRENT_SNAPSHOT_FORKED_NOW={str(obj['current_snapshot_forked_now']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_RECORD_COUNT={obj['future_snapshot_fork_record_count']}")
print(f"NEW_SNAPSHOT_RECORD_COUNT={obj['new_snapshot_record_count']}")
print(f"NO_UNFINALIZED_FORK_RECORDS={str(obj['no_unfinalized_fork_records']).lower()}")
print(f"NO_UNADJUDICATED_FORK_RECORDS={str(obj['no_unadjudicated_fork_records']).lower()}")
print(f"NO_UNTERMINALIZED_FORK_RECORDS={str(obj['no_unterminalized_fork_records']).lower()}")
print(f"NO_UNPERMANENT_FORK_RECORDS={str(obj['no_unpermanent_fork_records']).lower()}")
print(f"CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_MUTABLE={str(obj['current_zero_future_snapshot_fork_ledger_mutable']).lower()}")
print(f"PERMANENCE_SEAL_DOES_NOT_REOPEN_INTAKE={str(obj['permanence_seal_does_not_reopen_intake']).lower()}")
print(f"PERMANENCE_SEAL_DOES_NOT_OPEN_FUTURE_FORK_GATE={str(obj['permanence_seal_does_not_open_future_fork_gate']).lower()}")
print(f"PERMANENCE_SEAL_DOES_NOT_CREATE_NEW_SNAPSHOT={str(obj['permanence_seal_does_not_create_new_snapshot']).lower()}")
print(f"PERMANENCE_SEAL_DOES_NOT_MUTATE_CURRENT_SNAPSHOT={str(obj['permanence_seal_does_not_mutate_current_snapshot']).lower()}")
print(f"PERMANENCE_SEAL_DOES_NOT_MUTATE_TERMINAL_LEDGER={str(obj['permanence_seal_does_not_mutate_terminal_ledger']).lower()}")
print(f"AUTHORITY_SATISFIED={str(obj['authority_satisfied']).lower()}")
print(f"MAY_ADVANCE_NOW={str(obj['may_advance_now']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
PY
