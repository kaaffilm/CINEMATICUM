#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
import json
from pathlib import Path

STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
CASE_ID = "CASE_001_THE_LAST_RENDER"
ROOT = Path(".")

def load(path):
    p = ROOT / path
    if not p.exists():
        raise SystemExit(f"missing required file: {path}")
    return json.loads(p.read_text(encoding="utf-8"))

required = [
    "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA.json",
    "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR.json",
    "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS.json",
    "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY.json",
    "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER.json",
    "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_ENFORCEMENT_GATE.json",
    "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_ENFORCEMENT_GATE_LAW.json",
    "CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_ENFORCEMENT_GATE_STATUS.json",
]
for path in required:
    load(path)

gate = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_ENFORCEMENT_GATE.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_ENFORCEMENT_GATE_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_ENFORCEMENT_GATE_STATUS.json")
decision = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER.json")
current = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

current_state = current.get("current_state") or current.get("active_current_state") or current.get("state")
assert current_state == STATE

assert gate["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_ENFORCEMENT_GATE"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_ENFORCEMENT_GATE_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_ENFORCEMENT_GATE_STATUS"

for obj in (gate, law, status):
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == STATE
    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False

assert gate["gate_scope"] == "FUTURE_ACCEPTED_REOPENING_REQUESTS_ONLY"
assert gate["requires_reopening_request_schema"] is True
assert gate["requires_reopening_request_validator"] is True
assert gate["requires_reopening_request_rejection_corpus"] is True
assert gate["requires_reopening_request_rejection_taxonomy"] is True
assert gate["requires_reopening_request_decision_ledger"] is True
assert gate["requires_valid_reopening_request"] is True
assert gate["requires_recorded_reopening_decision"] is True
assert gate["requires_accepted_reopening_decision_for_reopening"] is True

for obj in (gate, status):
    assert obj["live_reopening_request_count"] == 0
    assert obj["valid_reopening_request_count"] == 0
    assert obj["decision_record_count"] == 0
    assert obj["accepted_reopening_request_count"] == 0
    assert obj["rejected_reopening_request_count"] == 0
    assert obj["all_live_reopening_requests_have_decisions"] is True
    assert obj["accepted_reopening_request_present"] is False
    assert obj["enforcement_gate_passed"] is False
    assert obj["reopening_gate_open_now"] is False
    assert obj["enforcement_gate_does_not_reopen_intake"] is True
    assert obj["silent_reopening_forbidden"] is True

assert decision["all_live_reopening_requests_have_decisions"] is True
assert decision["accepted_reopening_request_present"] is False
assert decision["decision_ledger_does_not_reopen_intake"] is True
assert decision["reopening_gate_open_now"] is False

assert law["accepted_reopening_request_required_before_reopening_gate_open"] is True
assert law["valid_reopening_request_required_before_acceptance"] is True
assert law["recorded_reopening_decision_required_before_enforcement"] is True
assert law["reopening_request_decision_ledger_required"] is True
assert law["silent_reopening_forbidden"] is True
assert law["enforcement_gate_does_not_reopen_intake"] is True
assert law["enforcement_gate_does_not_satisfy_authority"] is True
assert law["enforcement_gate_does_not_issue_motion_picture"] is True

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST ENFORCEMENT GATE: PASS")
print(f"CURRENT_STATE={STATE}")
print("GATE_SCOPE=FUTURE_ACCEPTED_REOPENING_REQUESTS_ONLY")
print("LIVE_REOPENING_REQUEST_COUNT=0")
print("VALID_REOPENING_REQUEST_COUNT=0")
print("DECISION_RECORD_COUNT=0")
print("ACCEPTED_REOPENING_REQUEST_COUNT=0")
print("REJECTED_REOPENING_REQUEST_COUNT=0")
print("ALL_LIVE_REOPENING_REQUESTS_HAVE_DECISIONS=true")
print("ACCEPTED_REOPENING_REQUEST_PRESENT=false")
print("ENFORCEMENT_GATE_PASSED=false")
print("REOPENING_GATE_OPEN_NOW=false")
print("ENFORCEMENT_GATE_DOES_NOT_REOPEN_INTAKE=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
