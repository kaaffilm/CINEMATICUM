#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"

OBJECT_PATH = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_CLOSURE_SEAL.json")
LAW_PATH = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_CLOSURE_SEAL_LAW.json")
STATUS_PATH = Path("CASES") / CASE_ID / "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_CLOSURE_SEAL_STATUS.json"
DECISION_LEDGER_PATH = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER.json")
ENFORCEMENT_GATE_PATH = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_ENFORCEMENT_GATE.json")

def load(path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(path.read_text())

obj = load(OBJECT_PATH)
law = load(LAW_PATH)
status = load(STATUS_PATH)
decision = load(DECISION_LEDGER_PATH)
gate = load(ENFORCEMENT_GATE_PATH)

assert obj["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_CLOSURE_SEAL"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_CLOSURE_SEAL_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_CLOSURE_SEAL_STATUS"

assert obj["case_id"] == CASE_ID
assert status["case_id"] == CASE_ID
assert obj["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

assert obj["closure_scope"] == "CURRENT_ZERO_REOPENING_REQUEST_SNAPSHOT_ONLY"
assert status["closure_scope"] == "CURRENT_ZERO_REOPENING_REQUEST_SNAPSHOT_ONLY"
assert law["closure_scope"] == "CURRENT_ZERO_REOPENING_REQUEST_SNAPSHOT_ONLY"

assert obj["reopening_request_stack_closed"] is True
assert status["reopening_request_stack_closed"] is True
assert obj["required_reopening_request_layer_count"] == 6
assert status["required_reopening_request_layer_count"] == 6

assert decision["decision_ledger_does_not_reopen_intake"] is True
assert gate["enforcement_gate_does_not_reopen_intake"] is True

for record in (obj, status):
    assert record["live_reopening_request_count"] == 0
    assert record["valid_reopening_request_count"] == 0
    assert record["decision_record_count"] == 0
    assert record["accepted_reopening_request_count"] == 0
    assert record["rejected_reopening_request_count"] == 0
    assert record["all_live_reopening_requests_have_decisions"] is True
    assert record["accepted_reopening_request_present"] is False
    assert record["enforcement_gate_passed"] is False
    assert record["reopening_gate_open_now"] is False
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["issued"] is False
    assert record["media_present"] is False

assert obj["closure_seal_does_not_reopen_intake"] is True
assert obj["closure_seal_does_not_satisfy_authority"] is True
assert obj["closure_seal_does_not_advance_state"] is True
assert law["closure_may_reopen_intake"] is False
assert law["closure_may_satisfy_authority"] is False
assert law["closure_may_advance_state"] is False
assert law["closure_may_issue_motion_picture"] is False

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST CLOSURE SEAL: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"CLOSURE_SCOPE={obj['closure_scope']}")
print(f"REOPENING_REQUEST_STACK_CLOSED={str(obj['reopening_request_stack_closed']).lower()}")
print(f"REQUIRED_REOPENING_REQUEST_LAYER_COUNT={obj['required_reopening_request_layer_count']}")
print(f"LIVE_REOPENING_REQUEST_COUNT={obj['live_reopening_request_count']}")
print(f"VALID_REOPENING_REQUEST_COUNT={obj['valid_reopening_request_count']}")
print(f"DECISION_RECORD_COUNT={obj['decision_record_count']}")
print(f"ACCEPTED_REOPENING_REQUEST_COUNT={obj['accepted_reopening_request_count']}")
print(f"REJECTED_REOPENING_REQUEST_COUNT={obj['rejected_reopening_request_count']}")
print(f"ENFORCEMENT_GATE_PASSED={str(obj['enforcement_gate_passed']).lower()}")
print(f"REOPENING_GATE_OPEN_NOW={str(obj['reopening_gate_open_now']).lower()}")
print(f"CLOSURE_SEAL_DOES_NOT_REOPEN_INTAKE={str(obj['closure_seal_does_not_reopen_intake']).lower()}")
print(f"AUTHORITY_SATISFIED={str(obj['authority_satisfied']).lower()}")
print(f"MAY_ADVANCE_NOW={str(obj['may_advance_now']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
PY
