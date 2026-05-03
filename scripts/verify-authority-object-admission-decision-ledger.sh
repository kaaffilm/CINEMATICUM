#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")

def load(path: str):
    p = ROOT / path
    assert p.exists(), path
    return json.loads(p.read_text(encoding="utf-8"))

def load_optional(path: str):
    p = ROOT / path
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

ledger = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_STATUS.json")
docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
state_index = load_optional("CINEMATICUM_CURRENT_STATE_INDEX.json")

def g(obj, *names, default=None):
    for name in names:
        if name in obj:
            return obj[name]
    return default

def count(obj, *names):
    value = g(obj, *names, default=0)
    assert isinstance(value, int), names
    return value

def flag(obj, *names):
    value = g(obj, *names, default=False)
    assert isinstance(value, bool), names
    return value

def reason_code(item):
    return item["code"] if isinstance(item, dict) else item

current_state = (
    g(ledger, "current_state", "active_current_state")
    or g(status, "current_state", "active_current_state")
    or g(state_index, "active_current_state", "current_state")
)
assert current_state == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED", current_state

admission_count = count(ledger, "admission_request_count", "live_admission_request_count")
live_admission_count = count(ledger, "live_admission_request_count", "admission_request_count")
decision_count = count(ledger, "decision_record_count", "admission_decision_count")
accepted_count = count(ledger, "accepted_decision_count")
rejected_count = count(ledger, "rejected_decision_count")

assert admission_count == live_admission_count
assert decision_count == accepted_count + rejected_count

assert flag(ledger, "admission_requests_present", "live_admission_requests_present") is (admission_count > 0)
assert flag(ledger, "decision_records_present") is (decision_count > 0)
assert flag(ledger, "accepted_decisions_present") is (accepted_count > 0)
assert flag(ledger, "rejected_decisions_present") is (rejected_count > 0)

assert flag(ledger, "all_live_requests_have_decisions")
assert flag(ledger, "all_accepted_decisions_have_valid_requests")
assert flag(ledger, "all_rejected_decisions_have_canonical_reasons")

assert count(docket, "admission_request_count") == admission_count
assert count(validator, "admission_request_count") == admission_count

taxonomy_codes = {reason_code(item) for item in taxonomy["canonical_rejection_reasons"]}
assert all(isinstance(code, str) and code for code in taxonomy_codes)

for record in ledger.get("decision_records", []):
    assert record["decision"] in {"ACCEPTED", "REJECTED"}
    if record["decision"] == "REJECTED":
        assert record["rejection_reason"] in taxonomy_codes

for obj in (ledger, status):
    assert g(obj, "current_state", "active_current_state", default=current_state) == current_state
    assert count(obj, "admission_request_count", "live_admission_request_count") == admission_count
    assert count(obj, "decision_record_count", "admission_decision_count") == decision_count
    assert count(obj, "accepted_decision_count") == accepted_count
    assert count(obj, "rejected_decision_count") == rejected_count
    assert flag(obj, "authority_satisfied") is False
    assert flag(obj, "may_advance_now") is False
    assert flag(obj, "release_candidate_ready") is False
    assert flag(obj, "issued") is False
    assert flag(obj, "media_present") is False

law_declared = g(law, "authority_object_admission_decision_ledger_law_declared", "law_declared", default=True)
assert isinstance(law_declared, bool)
assert law_declared is True
assert Path("AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.md").exists()
assert Path("authority_object_admission_decisions/README.md").exists()

print("CINEMATICUM AUTHORITY OBJECT ADMISSION DECISION LEDGER: PASS")
print(f"CURRENT_STATE={current_state}")
print(f"ADMISSION_REQUEST_COUNT={admission_count}")
print(f"DECISION_RECORD_COUNT={decision_count}")
print(f"ACCEPTED_DECISION_COUNT={accepted_count}")
print(f"REJECTED_DECISION_COUNT={rejected_count}")
print(f"ALL_LIVE_REQUESTS_HAVE_DECISIONS={str(flag(ledger, 'all_live_requests_have_decisions')).lower()}")
print(f"AUTHORITY_SATISFIED={str(flag(ledger, 'authority_satisfied')).lower()}")
print(f"MAY_ADVANCE_NOW={str(flag(ledger, 'may_advance_now')).lower()}")
print(f"ISSUED={str(flag(ledger, 'issued')).lower()}")
print(f"MEDIA_PRESENT={str(flag(ledger, 'media_present')).lower()}")
PY
