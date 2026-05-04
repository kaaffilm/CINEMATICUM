#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
CASE_ID = "CASE_001_THE_LAST_RENDER"

SEAL = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL.json")
LAW = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL_LAW.json")
STATUS = Path("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL_STATUS.json")
DOC = Path("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL.md")

CLOSURE = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json")
CLOSURE_STATUS = Path("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_STATUS.json")
GATE = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE.json")
LEDGER = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json")

REQUIRED = [
    SEAL,
    LAW,
    STATUS,
    DOC,
    CLOSURE,
    CLOSURE_STATUS,
    GATE,
    LEDGER,
    Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json"),
    Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json"),
    Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json"),
    Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json"),
]

def load(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

def require_file(path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")

def require_equal(doc, key, expected, name):
    actual = doc.get(key)
    if actual != expected:
        raise AssertionError(f"{name}.{key} expected {expected!r}, got {actual!r}")

def require_true(doc, key, name):
    if doc.get(key) is not True:
        raise AssertionError(f"{name}.{key} is not true")

def require_false(doc, key, name):
    if doc.get(key) is not False:
        raise AssertionError(f"{name}.{key} is not false")

def require_zero(doc, key, name):
    if doc.get(key) != 0:
        raise AssertionError(f"{name}.{key} expected 0, got {doc.get(key)!r}")

for path in REQUIRED:
    require_file(path)

seal = load(SEAL)
law = load(LAW)
status = load(STATUS)
closure = load(CLOSURE)
closure_status = load(CLOSURE_STATUS)
gate = load(GATE)
ledger = load(LEDGER)

for name, doc in [("seal", seal), ("law", law), ("status", status)]:
    require_equal(doc, "jurisdiction", "CINEMATICUM", name)
    require_equal(doc, "case_id", CASE_ID, name)
    require_equal(doc, "current_state", CURRENT_STATE, name)
    require_true(doc, "sealed", name)
    require_false(doc, "authority_satisfied", name)
    require_false(doc, "may_advance_now", name)
    require_false(doc, "release_candidate_ready", name)
    require_false(doc, "issued", name)
    require_false(doc, "media_present", name)

require_equal(seal, "object_id", "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL", "seal")
require_equal(seal, "object_type", "AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL", "seal")
require_equal(seal, "finality_scope", "CURRENT_ZERO_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_SNAPSHOT_ONLY", "seal")
require_equal(law, "object_id", "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL_LAW", "law")
require_equal(law, "scope", "CURRENT_ZERO_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_SNAPSHOT_ONLY", "law")
require_equal(status, "object_id", "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL_STATUS", "status")
require_equal(status, "scope", "CURRENT_ZERO_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_SNAPSHOT_ONLY", "status")

for name, doc in [("closure", closure), ("closure_status", closure_status)]:
    require_true(doc, "admission_stack_closed", name)
    require_true(doc, "closure_seal_declared", name)
    require_false(doc, "enforcement_gate_passed", name)
    require_false(doc, "authority_satisfied", name)
    require_false(doc, "may_advance_now", name)
    require_false(doc, "issued", name)
    require_false(doc, "media_present", name)

for name, doc in [("seal", seal), ("status", status)]:
    require_equal(doc, "admission_stack_layer_count", 7, name)
    require_true(doc, "real_case_authority_intake_open", name)
    require_true(doc, "admission_stack_closed", name)
    require_true(doc, "closure_seal_declared", name)
    require_true(doc, "current_zero_admission_snapshot_final", name)
    require_false(doc, "current_zero_admission_snapshot_mutable", name)
    require_true(doc, "future_valid_admission_requests_allowed_under_law", name)
    require_true(doc, "future_valid_admission_requests_require_explicit_request", name)
    require_true(doc, "future_valid_admission_requests_require_validation", name)
    require_true(doc, "future_valid_admission_requests_require_decision", name)
    require_true(doc, "future_valid_admission_requests_require_enforcement_gate", name)
    require_true(doc, "future_valid_admission_requests_do_not_mutate_current_zero_snapshot", name)
    require_true(doc, "all_live_admission_requests_have_decisions", name)
    require_true(doc, "no_unadjudicated_admission_records", name)
    require_false(doc, "enforcement_gate_passed", name)
    for key in [
        "live_admission_request_count",
        "valid_admission_request_count",
        "invalid_admission_request_count",
        "decision_record_count",
        "accepted_decision_count",
        "rejected_decision_count",
        "accepted_authority_object_count",
        "instantiated_authority_object_count"
    ]:
        require_zero(doc, key, name)

for key in [
    "finality_seal_required_after_closure_seal",
    "seals_current_zero_admission_snapshot",
    "current_zero_admission_snapshot_final",
    "does_not_bar_future_valid_admission_requests_under_law",
    "future_valid_admission_requests_allowed_under_law",
    "future_valid_admission_requests_require_explicit_request",
    "future_valid_admission_requests_require_validation",
    "future_valid_admission_requests_require_decision",
    "future_valid_admission_requests_require_enforcement_gate",
    "future_valid_admission_requests_do_not_mutate_current_zero_snapshot",
    "requires_closed_admission_stack",
    "requires_zero_live_admission_requests",
    "requires_zero_valid_admission_requests",
    "requires_zero_decision_records",
    "requires_zero_accepted_decisions",
    "requires_zero_instantiated_authority_objects",
    "requires_no_unadjudicated_admission_records",
    "finality_seal_does_not_create_live_requests",
    "finality_seal_does_not_validate_requests",
    "finality_seal_does_not_create_decision_records",
    "finality_seal_does_not_accept_requests",
    "finality_seal_does_not_reject_live_requests",
    "finality_seal_does_not_instantiate_authority_objects",
    "finality_seal_does_not_satisfy_authority",
    "finality_seal_does_not_advance_state",
    "finality_seal_does_not_issue_motion_picture",
    "finality_seal_does_not_admit_media",
    "finality_seal_does_not_create_release_candidate",
    "finality_seal_does_not_reopen_current_snapshot",
    "finality_seal_does_not_create_new_snapshot"
]:
    require_true(law, key, "law")

require_false(law, "current_zero_admission_snapshot_mutable", "law")
require_false(gate, "enforcement_gate_passed", "gate")
require_false(gate, "authority_satisfied", "gate")
require_false(gate, "may_advance_now", "gate")
require_false(gate, "issued", "gate")
require_false(gate, "media_present", "gate")

if ledger.get("decision_records") != []:
    raise AssertionError("decision ledger must remain empty for current zero-request snapshot")

doc = DOC.read_text(encoding="utf-8")
for token in [
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL",
    "current zero real-case authority-object admission snapshot",
    "no live admission requests",
    "no decision records",
    "no unadjudicated admission records",
    "future valid admission requests remain allowed under law",
    "future valid admission requests cannot mutate this snapshot",
    "no motion picture is issued",
    "no media is admitted"
]:
    if token not in doc:
        raise AssertionError(f"documentation missing token: {token}")

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION FINALITY SEAL: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("FINALITY_SCOPE=CURRENT_ZERO_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_SNAPSHOT_ONLY")
print("ADMISSION_STACK_LAYER_COUNT=7")
print("ADMISSION_STACK_CLOSED=true")
print("CLOSURE_SEAL_DECLARED=true")
print("CURRENT_ZERO_ADMISSION_SNAPSHOT_FINAL=true")
print("CURRENT_ZERO_ADMISSION_SNAPSHOT_MUTABLE=false")
print("FUTURE_VALID_ADMISSION_REQUESTS_ALLOWED_UNDER_LAW=true")
print("FUTURE_VALID_ADMISSION_REQUESTS_DO_NOT_MUTATE_CURRENT_ZERO_SNAPSHOT=true")
print("LIVE_ADMISSION_REQUEST_COUNT=0")
print("VALID_ADMISSION_REQUEST_COUNT=0")
print("DECISION_RECORD_COUNT=0")
print("ACCEPTED_DECISION_COUNT=0")
print("REJECTED_DECISION_COUNT=0")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("NO_UNADJUDICATED_ADMISSION_RECORDS=true")
print("ENFORCEMENT_GATE_PASSED=false")
print("FINALITY_SEAL_DOES_NOT_SATISFY_AUTHORITY=true")
print("FINALITY_SEAL_DOES_NOT_ADVANCE_STATE=true")
print("FINALITY_SEAL_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("FINALITY_SEAL_DOES_NOT_ADMIT_MEDIA=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
