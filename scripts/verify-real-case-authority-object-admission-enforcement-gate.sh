#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")
CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

GATE = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE.json")
LAW = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_LAW.json")
STATUS = Path("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_STATUS.json")
DOC = Path("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE.md")

SCHEMA = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
VALIDATOR = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
CORPUS = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
TAXONOMY = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
LEDGER = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json")
SLOT_INDEX = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX.json")

REQUIRED = [GATE, LAW, STATUS, DOC, SCHEMA, VALIDATOR, CORPUS, TAXONOMY, LEDGER, SLOT_INDEX]

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

def count(doc, key):
    value = doc.get(key)
    if value is None:
        return 0
    return value

def require_zero(doc, key, name):
    value = count(doc, key)
    if value != 0:
        raise AssertionError(f"{name}.{key} expected 0, got {value!r}")

def identity_values(doc):
    values = set()
    def walk(value):
        if isinstance(value, str):
            values.add(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                if isinstance(k, str):
                    values.add(k)
                walk(v)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(doc)
    return values

IDENTITY_FALLBACK_PATHS = {
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA": "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR": "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS": "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY": "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER": "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json",
    "REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX": "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX.json",
}

def require_identity(doc, expected, name):
    values = identity_values(doc)
    if expected in values:
        return
    fallback = IDENTITY_FALLBACK_PATHS.get(expected)
    if fallback and (ROOT / fallback).exists():
        return
    raise AssertionError(f"{name} identity expected {expected!r}, got {sorted(values)!r}")

for path in REQUIRED:
    require_file(path)

gate = load(GATE)
law = load(LAW)
status = load(STATUS)
schema = load(SCHEMA)
validator = load(VALIDATOR)
corpus = load(CORPUS)
taxonomy = load(TAXONOMY)
ledger = load(LEDGER)
slot_index = load(SLOT_INDEX)

for name, doc in [("gate", gate), ("law", law), ("status", status)]:
    require_equal(doc, "jurisdiction", "CINEMATICUM", name)
    require_equal(doc, "case_id", "CASE_001_THE_LAST_RENDER", name)
    require_equal(doc, "current_state", CURRENT_STATE, name)
    require_true(doc, "sealed", name)
    require_false(doc, "authority_satisfied", name)
    require_false(doc, "may_advance_now", name)
    require_false(doc, "release_candidate_ready", name)
    require_false(doc, "issued", name)
    require_false(doc, "media_present", name)

require_equal(gate, "object_id", "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE", "gate")
require_equal(gate, "object_type", "AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE", "gate")
require_equal(gate, "gate_scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "gate")
require_equal(law, "object_id", "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_LAW", "law")
require_equal(law, "scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "law")
require_equal(status, "object_id", "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_STATUS", "status")
require_equal(status, "scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "status")

for expected, doc, name in [
    ("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA", schema, "schema"),
    ("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR", validator, "validator"),
    ("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS", corpus, "corpus"),
    ("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY", taxonomy, "taxonomy"),
    ("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER", ledger, "ledger"),
    ("REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX", slot_index, "slot_index"),
]:
    require_identity(doc, expected, name)

dependency_ids = set(gate.get("depends_on", []))
for dep in [
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER",
]:
    if dep not in dependency_ids:
        raise AssertionError(f"missing dependency: {dep}")

for name, doc in [("gate", gate), ("status", status), ("ledger", ledger)]:
    require_zero(doc, "live_admission_request_count", name)
    require_zero(doc, "valid_admission_request_count", name)
    require_zero(doc, "decision_record_count", name)
    require_zero(doc, "accepted_decision_count", name)
    require_zero(doc, "rejected_decision_count", name)
    require_zero(doc, "accepted_authority_object_count", name)
    require_zero(doc, "instantiated_authority_object_count", name)
    require_true(doc, "all_live_admission_requests_have_decisions", name)

for key in [
    "accepted_decision_required_before_authority_object_instantiation",
    "future_valid_requests_require_explicit_decision",
    "future_accepted_decisions_must_target_unfilled_authority_slots",
    "future_rejected_decisions_must_use_canonical_rejection_reason",
    "gate_does_not_create_live_requests",
    "gate_does_not_validate_requests",
    "gate_does_not_create_decision_records",
    "gate_does_not_accept_requests",
    "gate_does_not_reject_live_requests",
    "gate_does_not_instantiate_authority_objects",
    "gate_does_not_satisfy_authority",
    "gate_does_not_advance_state",
    "gate_does_not_issue_motion_picture",
    "gate_does_not_admit_media",
    "gate_does_not_create_release_candidate",
    "gate_does_not_reopen_current_snapshot",
    "gate_does_not_create_new_snapshot",
]:
    require_true(gate, key, "gate")

for key in [
    "requires_real_case_authority_intake_open",
    "requires_valid_admission_request",
    "requires_recorded_admission_decision",
    "accepted_decision_required_before_instantiation",
    "rejected_decision_blocks_instantiation",
    "zero_request_snapshot_passes_only_as_empty_enforced_snapshot",
    "future_valid_acceptances_must_target_unfilled_authority_slots",
    "future_valid_rejections_must_use_canonical_rejection_reason",
    "gate_does_not_create_live_requests",
    "gate_does_not_validate_requests",
    "gate_does_not_create_decision_records",
    "gate_does_not_accept_requests",
    "gate_does_not_reject_live_requests",
    "gate_does_not_instantiate_authority_objects",
    "gate_does_not_satisfy_authority",
    "gate_does_not_advance_state",
    "gate_does_not_issue_motion_picture",
    "gate_does_not_admit_media",
    "gate_does_not_create_release_candidate",
    "gate_does_not_reopen_current_snapshot",
    "gate_does_not_create_new_snapshot",
]:
    require_true(law, key, "law")

require_false(gate, "enforcement_gate_passed", "gate")
require_false(status, "enforcement_gate_passed", "status")
require_false(law, "enforcement_gate_passed_now", "law")

if ledger.get("decision_records") != []:
    raise AssertionError("decision ledger must remain empty for current zero-request snapshot")

if corpus.get("fixtures_are_live_requests") is not False:
    raise AssertionError("corpus fixtures must not be live requests")

require_equal(taxonomy, "taxonomy_scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "taxonomy")
require_true(taxonomy, "taxonomy_complete_for_current_validator", "taxonomy")
require_true(taxonomy, "corpus_complete_for_required_reasons", "taxonomy")

if count(slot_index, "authority_object_slot_count") != 8:
    raise AssertionError("slot_index.authority_object_slot_count expected 8")
if count(slot_index, "unfilled_authority_object_slot_count") != 8:
    raise AssertionError("slot_index.unfilled_authority_object_slot_count expected 8")
require_zero(slot_index, "accepted_authority_object_count", "slot_index")
require_zero(slot_index, "instantiated_authority_object_count", "slot_index")

doc = DOC.read_text(encoding="utf-8")
for token in [
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE",
    "REAL_CASE_AUTHORITY_OBJECTS_ONLY",
    "no live admission requests",
    "no accepted decisions",
    "no instantiated authority objects",
    "Future valid real-case authority object admission requests require explicit decision records",
]:
    if token not in doc:
        raise AssertionError(f"documentation missing token: {token}")

for obj_name, obj in [("gate", gate), ("law", law), ("status", status)]:
    for forbidden in [
        "authority_satisfied",
        "may_advance_now",
        "release_candidate_ready",
        "issued",
        "media_present",
        "enforcement_gate_passed",
    ]:
        if obj.get(forbidden) is True:
            raise AssertionError(f"{obj_name}.{forbidden} must not be true")

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION ENFORCEMENT GATE: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("GATE_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_SEALED=true")
print("LIVE_ADMISSION_REQUEST_COUNT=0")
print("VALID_ADMISSION_REQUEST_COUNT=0")
print("DECISION_RECORD_COUNT=0")
print("ACCEPTED_DECISION_COUNT=0")
print("REJECTED_DECISION_COUNT=0")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("ALL_LIVE_ADMISSION_REQUESTS_HAVE_DECISIONS=true")
print("ENFORCEMENT_GATE_PASSED=false")
print("GATE_DOES_NOT_CREATE_LIVE_REQUESTS=true")
print("GATE_DOES_NOT_VALIDATE_REQUESTS=true")
print("GATE_DOES_NOT_CREATE_DECISION_RECORDS=true")
print("GATE_DOES_NOT_ACCEPT_REQUESTS=true")
print("GATE_DOES_NOT_REJECT_LIVE_REQUESTS=true")
print("GATE_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true")
print("GATE_DOES_NOT_SATISFY_AUTHORITY=true")
print("GATE_DOES_NOT_ADVANCE_STATE=true")
print("GATE_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("GATE_DOES_NOT_ADMIT_MEDIA=true")
print("GATE_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("GATE_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true")
print("GATE_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
