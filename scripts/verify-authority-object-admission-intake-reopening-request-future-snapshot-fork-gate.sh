#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"

OBJ = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_GATE.json")
LAW = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_GATE_LAW.json")
STATUS = Path("CASES") / CASE_ID / "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_GATE_STATUS.json"
CONTINUITY = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_CONTINUITY_SEAL.json")
PERMANENCE = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_PERMANENCE_SEAL.json")

def load(path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(path.read_text())

obj = load(OBJ)
law = load(LAW)
status = load(STATUS)
continuity = load(CONTINUITY)
permanence = load(PERMANENCE)

assert obj["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_GATE"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_GATE_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_GATE_STATUS"

assert permanence["reopening_request_permanence_sealed"] is True
assert permanence["current_snapshot_mutable"] is False
assert permanence["future_valid_reopening_requests_create_new_snapshot"] is True
assert permanence["future_valid_reopening_requests_do_not_mutate_current_snapshot"] is True

assert continuity["continuity_scope"] == "FUTURE_VALID_REOPENING_REQUESTS_ONLY"
assert continuity["permanence_seal_present"] is True
assert continuity["current_snapshot_final"] is True
assert continuity["current_snapshot_mutable"] is False
assert continuity["future_valid_reopening_requests_allowed_under_law"] is True
assert continuity["future_valid_reopening_requests_require_explicit_request"] is True
assert continuity["future_valid_reopening_requests_require_validation"] is True
assert continuity["future_valid_reopening_requests_require_decision"] is True
assert continuity["future_valid_reopening_requests_require_enforcement_gate"] is True
assert continuity["future_valid_reopening_requests_create_new_snapshot"] is True
assert continuity["future_valid_reopening_requests_do_not_mutate_current_snapshot"] is True
assert continuity["future_continuity_seal_does_not_reopen_intake"] is True
assert continuity["authority_satisfied"] is False
assert continuity["may_advance_now"] is False

for record in (obj, status):
    assert record["case_id"] == CASE_ID
    assert record["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
    assert record["fork_scope"] == "FUTURE_VALID_REOPENING_REQUESTS_CREATE_NEW_SNAPSHOT_ONLY"
    assert record["future_continuity_seal_required"] is True
    assert record["future_continuity_seal_present"] is True
    assert record["permanence_seal_required"] is True
    assert record["permanence_seal_present"] is True
    assert record["current_snapshot_final"] is True
    assert record["current_snapshot_mutable"] is False
    assert record["current_snapshot_reopenable_by_future_request"] is False
    assert record["current_snapshot_reopenable_by_silence"] is False
    assert record["future_valid_reopening_requests_allowed_under_law"] is True
    assert record["future_valid_reopening_requests_require_explicit_request"] is True
    assert record["future_valid_reopening_requests_require_validation"] is True
    assert record["future_valid_reopening_requests_require_decision"] is True
    assert record["future_valid_reopening_requests_require_enforcement_gate"] is True
    assert record["future_valid_reopening_requests_create_new_snapshot"] is True
    assert record["future_valid_reopening_requests_fork_from_current_snapshot"] is True
    assert record["future_valid_reopening_requests_do_not_mutate_current_snapshot"] is True
    assert record["future_valid_reopening_requests_do_not_reopen_current_snapshot"] is True
    assert record["future_valid_reopening_requests_do_not_satisfy_current_authority"] is True
    assert record["future_valid_reopening_requests_do_not_advance_current_state"] is True
    assert record["silent_reopening_forbidden"] is True
    assert record["silent_snapshot_mutation_forbidden"] is True
    assert record["implicit_snapshot_fork_forbidden"] is True
    assert record["live_reopening_request_count"] == 0
    assert record["valid_reopening_request_count"] == 0
    assert record["decision_record_count"] == 0
    assert record["accepted_reopening_request_count"] == 0
    assert record["rejected_reopening_request_count"] == 0
    assert record["all_live_reopening_requests_have_decisions"] is True
    assert record["accepted_reopening_request_present"] is False
    assert record["enforcement_gate_passed"] is False
    assert record["reopening_gate_open_now"] is False
    assert record["future_snapshot_fork_gate_passed"] is False
    assert record["future_snapshot_fork_gate_does_not_reopen_intake"] is True
    assert record["future_snapshot_fork_gate_does_not_mutate_current_snapshot"] is True
    assert record["future_snapshot_fork_gate_does_not_satisfy_authority"] is True
    assert record["future_snapshot_fork_gate_does_not_advance_state"] is True
    assert record["future_snapshot_fork_gate_does_not_issue_motion_picture"] is True
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["issued"] is False
    assert record["media_present"] is False

assert law["fork_scope"] == "FUTURE_VALID_REOPENING_REQUESTS_CREATE_NEW_SNAPSHOT_ONLY"
assert law["future_snapshot_fork_requires_future_continuity_seal"] is True
assert law["future_snapshot_fork_requires_permanence_seal"] is True
assert law["current_snapshot_final"] is True
assert law["current_snapshot_mutation_forbidden"] is True
assert law["current_snapshot_reopening_by_future_request_forbidden"] is True
assert law["future_valid_reopening_requests_allowed_under_law"] is True
assert law["future_valid_reopening_requests_require_explicit_request"] is True
assert law["future_valid_reopening_requests_require_validation"] is True
assert law["future_valid_reopening_requests_require_decision"] is True
assert law["future_valid_reopening_requests_require_enforcement_gate"] is True
assert law["future_valid_reopening_requests_create_new_snapshot"] is True
assert law["future_valid_reopening_requests_fork_from_current_snapshot"] is True
assert law["future_valid_reopening_requests_do_not_mutate_current_snapshot"] is True
assert law["future_valid_reopening_requests_do_not_reopen_current_snapshot"] is True
assert law["future_valid_reopening_requests_do_not_satisfy_current_authority"] is True
assert law["future_valid_reopening_requests_do_not_advance_current_state"] is True
assert law["silent_reopening_forbidden"] is True
assert law["implicit_snapshot_fork_forbidden"] is True
assert law["future_snapshot_fork_gate_may_reopen_current_snapshot"] is False
assert law["future_snapshot_fork_gate_may_satisfy_authority"] is False
assert law["future_snapshot_fork_gate_may_advance_state"] is False
assert law["future_snapshot_fork_gate_may_issue_motion_picture"] is False

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK GATE: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"FORK_SCOPE={obj['fork_scope']}")
print(f"FUTURE_CONTINUITY_SEAL_PRESENT={str(obj['future_continuity_seal_present']).lower()}")
print(f"PERMANENCE_SEAL_PRESENT={str(obj['permanence_seal_present']).lower()}")
print(f"CURRENT_SNAPSHOT_FINAL={str(obj['current_snapshot_final']).lower()}")
print(f"CURRENT_SNAPSHOT_MUTABLE={str(obj['current_snapshot_mutable']).lower()}")
print(f"CURRENT_SNAPSHOT_REOPENABLE_BY_FUTURE_REQUEST={str(obj['current_snapshot_reopenable_by_future_request']).lower()}")
print(f"FUTURE_VALID_REOPENING_REQUESTS_CREATE_NEW_SNAPSHOT={str(obj['future_valid_reopening_requests_create_new_snapshot']).lower()}")
print(f"FUTURE_VALID_REOPENING_REQUESTS_FORK_FROM_CURRENT_SNAPSHOT={str(obj['future_valid_reopening_requests_fork_from_current_snapshot']).lower()}")
print(f"FUTURE_VALID_REOPENING_REQUESTS_DO_NOT_MUTATE_CURRENT_SNAPSHOT={str(obj['future_valid_reopening_requests_do_not_mutate_current_snapshot']).lower()}")
print(f"FUTURE_VALID_REOPENING_REQUESTS_DO_NOT_REOPEN_CURRENT_SNAPSHOT={str(obj['future_valid_reopening_requests_do_not_reopen_current_snapshot']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_PASSED={str(obj['future_snapshot_fork_gate_passed']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_DOES_NOT_REOPEN_INTAKE={str(obj['future_snapshot_fork_gate_does_not_reopen_intake']).lower()}")
print(f"AUTHORITY_SATISFIED={str(obj['authority_satisfied']).lower()}")
print(f"MAY_ADVANCE_NOW={str(obj['may_advance_now']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
PY
