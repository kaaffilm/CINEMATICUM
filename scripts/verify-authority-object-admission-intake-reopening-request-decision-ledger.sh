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
    "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER_LAW.json",
    "CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER_STATUS.json",
]
for path in required:
    load(path)

ledger = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER_STATUS.json")
current = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

def get(d, *keys, default=None):
    for key in keys:
        if key in d:
            return d[key]
    return default

current_state = get(current, "current_state", "active_current_state", "state", default=STATE)

assert current_state == STATE
assert ledger["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER_LAW"
assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER_STATUS"

for obj in (ledger, law, status):
    assert obj["case_id"] == CASE_ID
    assert obj["current_state"] == STATE
    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False

assert ledger["decision_scope"] == "FUTURE_VALID_REOPENING_REQUESTS_ONLY"
assert ledger["live_reopening_request_count"] == 0
assert ledger["valid_reopening_request_count"] == 0
assert ledger["decision_record_count"] == 0
assert ledger["accepted_reopening_request_count"] == 0
assert ledger["rejected_reopening_request_count"] == 0
assert ledger["decision_records"] == []
assert ledger["all_live_reopening_requests_have_decisions"] is True
assert ledger["accepted_reopening_request_present"] is False
assert ledger["decision_ledger_does_not_reopen_intake"] is True
assert ledger["silent_reopening_forbidden"] is True
assert ledger["reopening_gate_open_now"] is False

assert law["accepted_reopening_request_required_to_open_reopening_gate"] is True
assert law["silent_reopening_forbidden"] is True
assert law["decision_ledger_does_not_reopen_intake"] is True

assert status["all_live_reopening_requests_have_decisions"] is True
assert status["accepted_reopening_request_present"] is False
assert status["decision_ledger_does_not_reopen_intake"] is True
assert status["reopening_gate_open_now"] is False

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST DECISION LEDGER: PASS")
print(f"CURRENT_STATE={STATE}")
print("DECISION_SCOPE=FUTURE_VALID_REOPENING_REQUESTS_ONLY")
print("LIVE_REOPENING_REQUEST_COUNT=0")
print("VALID_REOPENING_REQUEST_COUNT=0")
print("DECISION_RECORD_COUNT=0")
print("ACCEPTED_REOPENING_REQUEST_COUNT=0")
print("REJECTED_REOPENING_REQUEST_COUNT=0")
print("ALL_LIVE_REOPENING_REQUESTS_HAVE_DECISIONS=true")
print("ACCEPTED_REOPENING_REQUEST_PRESENT=false")
print("DECISION_LEDGER_DOES_NOT_REOPEN_INTAKE=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
