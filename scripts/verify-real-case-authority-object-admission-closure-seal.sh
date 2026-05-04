#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
CASE_ID = "CASE_001_THE_LAST_RENDER"

SEAL = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json")
LAW = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_LAW.json")
STATUS = Path("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_STATUS.json")
DOC = Path("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.md")

SCHEMA = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
VALIDATOR = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
CORPUS = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
TAXONOMY = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
LEDGER = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json")
GATE = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE.json")
GATE_STATUS = Path("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_STATUS.json")

REQUIRED = [SEAL, LAW, STATUS, DOC, SCHEMA, VALIDATOR, CORPUS, TAXONOMY, LEDGER, GATE, GATE_STATUS]

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
ledger = load(LEDGER)
gate = load(GATE)
gate_status = load(GATE_STATUS)

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

require_equal(seal, "object_id", "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL", "seal")
require_equal(seal, "object_type", "AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL", "seal")
require_equal(seal, "seal_scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "seal")
require_equal(law, "object_id", "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_LAW", "law")
require_equal(law, "scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "law")
require_equal(status, "object_id", "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_STATUS", "status")
require_equal(status, "scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "status")

for name, doc in [("seal", seal), ("status", status)]:
    require_equal(doc, "admission_stack_layer_count", 6, name)
    require_true(doc, "real_case_authority_intake_open", name)
    require_true(doc, "admission_stack_closed", name)
    require_true(doc, "closure_seal_declared", name)
    require_true(doc, "all_live_admission_requests_have_decisions", name)
    require_false(doc, "enforcement_gate_passed", name)
    for key in [
        "live_admission_request_count",
        "valid_admission_request_count",
        "decision_record_count",
        "accepted_decision_count",
        "rejected_decision_count",
        "accepted_authority_object_count",
        "instantiated_authority_object_count"
    ]:
        require_zero(doc, key, name)

for key in [
    "closure_seal_required_after_enforcement_gate",
    "closure_seal_is_non_advancing",
    "closure_seal_is_not_authority_satisfaction",
    "closure_seal_is_not_release_readiness",
    "closure_seal_is_not_issuance",
    "requires_real_case_authority_intake_open",
    "requires_request_schema",
    "requires_request_validator",
    "requires_rejection_corpus",
    "requires_rejection_taxonomy",
    "requires_decision_ledger",
    "requires_enforcement_gate",
    "zero_request_snapshot_closes_as_empty_adjudicated_stack",
    "future_valid_requests_require_explicit_decision",
    "future_valid_acceptances_must_target_unfilled_authority_slots",
    "future_valid_rejections_must_use_canonical_rejection_reason",
    "closure_seal_does_not_create_live_requests",
    "closure_seal_does_not_validate_requests",
    "closure_seal_does_not_create_decision_records",
    "closure_seal_does_not_accept_requests",
    "closure_seal_does_not_reject_live_requests",
    "closure_seal_does_not_instantiate_authority_objects",
    "closure_seal_does_not_satisfy_authority",
    "closure_seal_does_not_advance_state",
    "closure_seal_does_not_issue_motion_picture",
    "closure_seal_does_not_admit_media",
    "closure_seal_does_not_create_release_candidate",
    "closure_seal_does_not_reopen_current_snapshot",
    "closure_seal_does_not_create_new_snapshot"
]:
    require_true(law, key, "law")

for key in [
    "future_valid_requests_require_explicit_decision",
    "future_accepted_decisions_must_target_unfilled_authority_slots",
    "future_rejected_decisions_must_use_canonical_rejection_reason",
    "closure_seal_does_not_create_live_requests",
    "closure_seal_does_not_validate_requests",
    "closure_seal_does_not_create_decision_records",
    "closure_seal_does_not_accept_requests",
    "closure_seal_does_not_reject_live_requests",
    "closure_seal_does_not_instantiate_authority_objects",
    "closure_seal_does_not_satisfy_authority",
    "closure_seal_does_not_advance_state",
    "closure_seal_does_not_issue_motion_picture",
    "closure_seal_does_not_admit_media",
    "closure_seal_does_not_create_release_candidate",
    "closure_seal_does_not_reopen_current_snapshot",
    "closure_seal_does_not_create_new_snapshot"
]:
    require_true(seal, key, "seal")

require_false(gate, "enforcement_gate_passed", "gate")
require_false(gate_status, "enforcement_gate_passed", "gate_status")
require_false(gate, "authority_satisfied", "gate")
require_false(gate_status, "authority_satisfied", "gate_status")
require_false(gate, "may_advance_now", "gate")
require_false(gate_status, "may_advance_now", "gate_status")
require_false(gate, "issued", "gate")
require_false(gate_status, "issued", "gate_status")
require_false(gate, "media_present", "gate")
require_false(gate_status, "media_present", "gate_status")

if ledger.get("decision_records") != []:
    raise AssertionError("decision ledger must remain empty for current zero-request snapshot")

doc = DOC.read_text(encoding="utf-8")
for token in [
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL",
    "adjudication boundary",
    "no live admission requests",
    "no accepted authority objects",
    "no instantiated authority objects",
    "no motion picture is issued",
    "no media is admitted",
    "Future valid real-case authority object admission requests"
]:
    if token not in doc:
        raise AssertionError(f"documentation missing token: {token}")

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION CLOSURE SEAL: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("CLOSURE_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_SEALED=true")
print("ADMISSION_STACK_LAYER_COUNT=6")
print("ADMISSION_STACK_CLOSED=true")
print("LIVE_ADMISSION_REQUEST_COUNT=0")
print("VALID_ADMISSION_REQUEST_COUNT=0")
print("DECISION_RECORD_COUNT=0")
print("ACCEPTED_DECISION_COUNT=0")
print("REJECTED_DECISION_COUNT=0")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("ALL_LIVE_ADMISSION_REQUESTS_HAVE_DECISIONS=true")
print("ENFORCEMENT_GATE_PASSED=false")
print("CLOSURE_SEAL_DOES_NOT_SATISFY_AUTHORITY=true")
print("CLOSURE_SEAL_DOES_NOT_ADVANCE_STATE=true")
print("CLOSURE_SEAL_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("CLOSURE_SEAL_DOES_NOT_ADMIT_MEDIA=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
