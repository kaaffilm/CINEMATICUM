#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"

OBJ = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FINALITY_SEAL.json")
LAW = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FINALITY_SEAL_LAW.json")
STATUS = Path("CASES") / CASE_ID / "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FINALITY_SEAL_STATUS.json"
CLOSURE = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_CLOSURE_SEAL.json")

def load(path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(path.read_text())

obj = load(OBJ)
law = load(LAW)
status = load(STATUS)
closure = load(CLOSURE)

assert obj["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FINALITY_SEAL"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FINALITY_SEAL_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FINALITY_SEAL_STATUS"

assert obj["case_id"] == CASE_ID
assert status["case_id"] == CASE_ID
assert obj["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
assert status["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"

assert obj["finality_scope"] == "CURRENT_ZERO_REOPENING_REQUEST_SNAPSHOT_ONLY"
assert status["finality_scope"] == "CURRENT_ZERO_REOPENING_REQUEST_SNAPSHOT_ONLY"
assert law["finality_scope"] == "CURRENT_ZERO_REOPENING_REQUEST_SNAPSHOT_ONLY"

assert closure["reopening_request_stack_closed"] is True
assert closure["current_snapshot_final"] is True
assert closure["no_unadjudicated_reopening_request_records"] is True
assert closure["closure_seal_does_not_reopen_intake"] is True

for record in (obj, status):
    assert record["closure_seal_required"] is True
    assert record["closure_seal_present"] is True
    assert record["reopening_request_stack_closed"] is True
    assert record["current_snapshot_final"] is True
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
    assert record["reopening_request_finality_sealed"] is True
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["issued"] is False
    assert record["media_present"] is False

assert obj["finality_seal_does_not_reopen_intake"] is True
assert obj["finality_seal_does_not_satisfy_authority"] is True
assert obj["finality_seal_does_not_advance_state"] is True

assert law["finality_requires_closure_seal"] is True
assert law["finality_requires_zero_live_reopening_requests"] is True
assert law["finality_requires_no_unadjudicated_reopening_request_records"] is True
assert law["finality_may_reopen_intake"] is False
assert law["finality_may_satisfy_authority"] is False
assert law["finality_may_advance_state"] is False
assert law["finality_may_issue_motion_picture"] is False

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FINALITY SEAL: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"FINALITY_SCOPE={obj['finality_scope']}")
print(f"REOPENING_REQUEST_STACK_CLOSED={str(obj['reopening_request_stack_closed']).lower()}")
print(f"CURRENT_SNAPSHOT_FINAL={str(obj['current_snapshot_final']).lower()}")
print(f"NO_UNADJUDICATED_REOPENING_REQUEST_RECORDS={str(obj['no_unadjudicated_reopening_request_records']).lower()}")
print(f"REOPENING_REQUEST_FINALITY_SEALED={str(obj['reopening_request_finality_sealed']).lower()}")
print(f"LIVE_REOPENING_REQUEST_COUNT={obj['live_reopening_request_count']}")
print(f"VALID_REOPENING_REQUEST_COUNT={obj['valid_reopening_request_count']}")
print(f"DECISION_RECORD_COUNT={obj['decision_record_count']}")
print(f"ENFORCEMENT_GATE_PASSED={str(obj['enforcement_gate_passed']).lower()}")
print(f"REOPENING_GATE_OPEN_NOW={str(obj['reopening_gate_open_now']).lower()}")
print(f"FINALITY_SEAL_DOES_NOT_REOPEN_INTAKE={str(obj['finality_seal_does_not_reopen_intake']).lower()}")
print(f"AUTHORITY_SATISFIED={str(obj['authority_satisfied']).lower()}")
print(f"MAY_ADVANCE_NOW={str(obj['may_advance_now']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
PY
