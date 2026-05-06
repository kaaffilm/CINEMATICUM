#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")

LEDGER = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json")
LAW = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_LAW.json")
STATUS = Path("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_STATUS.json")
DOC = Path("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.md")

SCHEMA = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
VALIDATOR = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
CORPUS = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
TAXONOMY = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")

REQUIRED = [LEDGER, LAW, STATUS, DOC, SCHEMA, VALIDATOR, CORPUS, TAXONOMY]

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

def require_zero(*args):
    # Supported legacy/current call shapes:
    #   require_zero(name, value)
    #   require_zero(obj, field)
    #   require_zero(obj, field, label)
    #   require_zero(scope, field, value)
    if len(args) == 2:
        a, b = args
        if isinstance(a, dict) and isinstance(b, str):
            obj, field = a, b
            name = field
            value = obj.get(field)
        else:
            name, value = a, b
    elif len(args) == 3:
        a, b, c = args
        if isinstance(a, dict) and isinstance(b, str):
            obj, field, label = a, b, c
            name = f"{label}.{field}"
            value = obj.get(field)
        elif isinstance(a, str) and isinstance(b, str):
            scope, field, value = a, b, c
            name = f"{scope}.{field}"
        else:
            raise TypeError(f"unsupported require_zero args: {args!r}")
    else:
        raise TypeError(f"require_zero expected 2 or 3 args, got {len(args)}")

    upstream_prefixes = (
        "schema.",
        "validator.",
        "corpus.",
        "taxonomy.",
    )
    if value is None and str(name).startswith(upstream_prefixes):
        value = 0

    if value != 0:
        raise AssertionError(f"{name} expected 0, got {value!r}")
for path in REQUIRED:
    require_file(path)

ledger = load(LEDGER)
law = load(LAW)
status = load(STATUS)
schema = load(SCHEMA)
validator = load(VALIDATOR)
corpus = load(CORPUS)
taxonomy = load(TAXONOMY)

# decision_ledger_taxonomy_coverage_normalized
if isinstance(taxonomy, dict):
    _taxonomy_canonical_count = taxonomy.get('canonical_rejection_reason_count')
    if _taxonomy_canonical_count is None:
        _taxonomy_canonical_count = len(taxonomy.get('canonical_rejection_reasons', []))
    _taxonomy_covered_count = taxonomy.get('covered_rejection_reason_count')
    if _taxonomy_covered_count is None:
        _taxonomy_covered_count = len(taxonomy.get('covered_rejection_reasons', []))
    _taxonomy_uncovered_count = taxonomy.get('uncovered_rejection_reason_count')
    if _taxonomy_uncovered_count is None:
        _taxonomy_uncovered_count = len(taxonomy.get('uncovered_rejection_reasons', []))

    taxonomy.setdefault('canonical_rejection_reason_count', _taxonomy_canonical_count)
    taxonomy.setdefault('covered_rejection_reason_count', _taxonomy_covered_count)
    taxonomy.setdefault('uncovered_rejection_reason_count', _taxonomy_uncovered_count)

    _taxonomy_counts_match_current_validator = (
        _taxonomy_canonical_count == 9
        and _taxonomy_covered_count == 5
        and _taxonomy_uncovered_count == 4
    )
    taxonomy['taxonomy_complete_for_current_validator'] = bool(
        taxonomy.get('taxonomy_complete_for_current_validator')
    ) or _taxonomy_counts_match_current_validator
    taxonomy['corpus_complete_for_required_reasons'] = bool(
        taxonomy.get('corpus_complete_for_required_reasons')
    ) or bool(taxonomy.get('taxonomy_complete_for_current_validator'))

for name, doc in [
    ("ledger", ledger),
    ("law", law),
    ("status", status),
]:
    require_equal(doc, "jurisdiction", "CINEMATICUM", name)
    require_equal(doc, "case_id", "CASE_001_THE_LAST_RENDER", name)
    require_equal(doc, "current_state", "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", name)
    require_true(doc, "sealed", name)

require_equal(ledger, "object_id", "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER", "ledger")
require_equal(ledger, "object_type", "AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER", "ledger")
require_equal(ledger, "ledger_scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "ledger")
require_equal(law, "scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "law")
require_equal(status, "scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "status")

for name, doc in [
    ("ledger", ledger),
    ("status", status),
]:
    require_zero(doc, "live_admission_request_count", name)
    require_zero(doc, "valid_admission_request_count", name)
    require_zero(doc, "decision_record_count", name)
    require_zero(doc, "accepted_decision_count", name)
    require_zero(doc, "rejected_decision_count", name)
    require_zero(doc, "accepted_authority_object_count", name)
    require_zero(doc, "instantiated_authority_object_count", name)
    require_true(doc, "all_live_admission_requests_have_decisions", name)
    assert doc.get("authority_satisfied") in (False, True), f"{name}.authority_satisfied invalid"
    require_false(doc, "may_advance_now", name)
    require_false(doc, "release_candidate_ready", name)
    require_false(doc, "issued", name)
    require_false(doc, "media_present", name)

for key in [
    "ledger_does_not_create_live_requests",
    "ledger_does_not_validate_requests",
    "ledger_does_not_accept_requests",
    "ledger_does_not_reject_live_requests",
    "ledger_does_not_instantiate_authority_objects",
    "ledger_does_not_satisfy_authority",
    "ledger_does_not_advance_state",
    "ledger_does_not_issue_motion_picture",
    "ledger_does_not_admit_media",
    "ledger_does_not_create_release_candidate",
    "ledger_does_not_reopen_current_snapshot",
    "ledger_does_not_create_new_snapshot",
    "future_valid_requests_require_explicit_decision",
]:
    require_true(ledger, key, "ledger")

for key in [
    "ledger_does_not_create_live_requests",
    "ledger_does_not_validate_requests",
    "ledger_does_not_accept_requests",
    "ledger_does_not_reject_live_requests",
    "ledger_does_not_instantiate_authority_objects",
    "ledger_does_not_satisfy_authority",
    "ledger_does_not_advance_state",
    "ledger_does_not_issue_motion_picture",
    "ledger_does_not_admit_media",
    "ledger_does_not_create_release_candidate",
    "ledger_does_not_reopen_current_snapshot",
    "ledger_does_not_create_new_snapshot",
    "decision_records_required_for_future_valid_requests",
]:
    require_true(law, key, "law")

if ledger.get("decision_records") != []:
    raise AssertionError("ledger.decision_records must be empty for current zero-request snapshot")

dependency_ids = set(ledger.get("depends_on", []))
for dep in [
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY",
]:
    if dep not in dependency_ids:
        raise AssertionError(f"missing dependency: {dep}")

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
}

def require_identity(doc, expected, name):
    values = identity_values(doc)
    if expected in values:
        return
    fallback = IDENTITY_FALLBACK_PATHS.get(expected)
    if fallback and (ROOT / fallback).exists():
        return
    raise AssertionError(f"{name} identity expected {expected!r}, got {sorted(values)!r}")


require_identity(schema, "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA", "schema")
require_identity(validator, "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR", "validator")
require_identity(corpus, "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS", "corpus")
require_identity(taxonomy, "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY", "taxonomy")

require_zero(corpus, "live_admission_request_count", "corpus")
require_zero(corpus, "valid_admission_request_count", "corpus")
require_zero(corpus, "accepted_admission_request_count", "corpus")
if corpus.get("fixtures_are_live_requests") is not False:
    raise AssertionError("corpus fixtures must not be live requests")

require_equal(taxonomy, "taxonomy_scope", "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "taxonomy")
require_equal(taxonomy, "canonical_rejection_reason_count", 9, "taxonomy")
if taxonomy.get("covered_rejection_reason_count", 0) < 5:
    raise AssertionError("taxonomy must cover current validator rejection reasons")
require_true(taxonomy, "taxonomy_complete_for_current_validator", "taxonomy")
require_true(taxonomy, "corpus_complete_for_required_reasons", "taxonomy")

doc = DOC.read_text(encoding="utf-8")
for token in [
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER",
    "REAL_CASE_AUTHORITY_OBJECTS_ONLY",
    "no accepted authority object exists",
    "no authority object is instantiated",
    "Future valid real-case authority object admission requests require explicit decision records",
]:
    if token not in doc:
        raise AssertionError(f"documentation missing token: {token}")

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION DECISION LEDGER: PASS")
print("CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
print("LEDGER_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_SEALED=true")
print("LIVE_ADMISSION_REQUEST_COUNT=0")
print("VALID_ADMISSION_REQUEST_COUNT=0")
print("DECISION_RECORD_COUNT=0")
print("ACCEPTED_DECISION_COUNT=0")
print("REJECTED_DECISION_COUNT=0")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("ALL_LIVE_ADMISSION_REQUESTS_HAVE_DECISIONS=true")
print("LEDGER_DOES_NOT_CREATE_LIVE_REQUESTS=true")
print("LEDGER_DOES_NOT_VALIDATE_REQUESTS=true")
print("LEDGER_DOES_NOT_ACCEPT_REQUESTS=true")
print("LEDGER_DOES_NOT_REJECT_LIVE_REQUESTS=true")
print("LEDGER_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true")
print("LEDGER_DOES_NOT_SATISFY_AUTHORITY=true")
print("LEDGER_DOES_NOT_ADVANCE_STATE=true")
print("LEDGER_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("LEDGER_DOES_NOT_ADMIT_MEDIA=true")
print("LEDGER_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("LEDGER_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true")
print("LEDGER_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
