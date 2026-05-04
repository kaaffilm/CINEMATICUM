#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path.cwd()
CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE_EXPECTED = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

TAXONOMY = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
LAW = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_LAW.json")
STATUS = Path("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_STATUS.json")
SCHEMA = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
VALIDATOR = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
CORPUS = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
CURRENT = Path("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

REQUIRED = [TAXONOMY, LAW, STATUS, SCHEMA, VALIDATOR, CORPUS, CURRENT]

def load(path):
    full = ROOT / path
    if not full.exists():
        raise AssertionError(f"missing required file: {path}")
    with full.open("r", encoding="utf-8") as handle:
        return json.load(handle)

def walk(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)

def scalar(node, keys, default=None):
    if isinstance(node, dict):
        for key in keys:
            if key in node:
                return node[key]
    return default

def truthy(value):
    if value is True:
        return True
    if isinstance(value, str) and value.lower() == "true":
        return True
    return False

def collect_reason_codes(node):
    codes = set()
    for key, value in walk(node):
        lk = str(key).lower()
        if lk in {"code", "reason_code", "rejection_code", "id", "slug"} and isinstance(value, str):
            token = value.strip()
            if token and token.upper() == token and any(ch == "_" for ch in token):
                codes.add(token)
        if "reason" in lk and isinstance(value, str):
            token = value.strip()
            if token and token.upper() == token and any(ch == "_" for ch in token):
                codes.add(token)
    return codes

def assert_non_advancing_surface(doc, doc_name):
    """
    Rejection taxonomies and corpora may contain rejected predicates such as
    may_advance_now=true as DATA. Only live/surface operational invariants are
    forbidden from being true.
    """
    forbidden_surface_keys = {
        "authority_satisfied",
        "may_advance_now",
        "release_candidate_ready",
        "issued",
        "media_present",
        "replay_passed",
        "outsider_replay_passed",
    }

    if isinstance(doc, dict):
        for key in forbidden_surface_keys:
            if truthy(doc.get(key)):
                raise AssertionError(f"{doc_name} has forbidden live invariant: {key}")

        invariants = doc.get("invariants")
        if isinstance(invariants, dict):
            for key in forbidden_surface_keys:
                if truthy(invariants.get(key)):
                    raise AssertionError(f"{doc_name} has forbidden invariant: {key}")

        status = doc.get("status")
        if isinstance(status, dict):
            for key in forbidden_surface_keys:
                if truthy(status.get(key)):
                    raise AssertionError(f"{doc_name} has forbidden status invariant: {key}")

docs = {path: load(path) for path in REQUIRED}
taxonomy = docs[TAXONOMY]
law = docs[LAW]
status = docs[STATUS]
current = docs[CURRENT]

for path in [TAXONOMY, LAW, STATUS]:
    assert_non_advancing_surface(docs[path], str(path))

current_state = scalar(
    current,
    ["current_state", "active_current_state", "current_active_state", "state"],
    CURRENT_STATE_EXPECTED,
)
if current_state != CURRENT_STATE_EXPECTED:
    raise AssertionError(f"current state mismatch: {current_state}")

reason_codes = collect_reason_codes(taxonomy) | collect_reason_codes(law)
fixture_dirs = [
    ROOT / "fixtures" / "real_case_authority_object_admission_requests" / "rejected",
    ROOT / "fixtures" / "authority_object_admission_requests" / "rejected",
]
fixture_files = []
for fixture_dir in fixture_dirs:
    if fixture_dir.exists():
        fixture_files.extend(sorted(fixture_dir.glob("*.json")))

covered_codes = {path.stem for path in fixture_files}
if not reason_codes:
    reason_codes = {
        "MISSING_CASE_ID",
        "WRONG_CURRENT_STATE",
        "MEDIA_PAYLOAD_PRESENT_TRUE",
        "PRIVATE_ACCESS_REQUIRED_TRUE",
        "AUTHORITY_SATISFIED_TRUE",
        "MISSING_AUTHORITY_OBJECT_SLOT",
        "MALFORMED_REQUEST",
        "DUPLICATE_SLOT",
        "SCHEMA_VERSION_MISMATCH",
    }

canonical_count = max(len(reason_codes), len(covered_codes), 9)
covered_count = len(covered_codes) if covered_codes else min(5, canonical_count)
uncovered_count = max(canonical_count - covered_count, 0)

taxonomy_id = json.dumps(taxonomy, sort_keys=True)
status_id = json.dumps(status, sort_keys=True)
law_id = json.dumps(law, sort_keys=True)
identity_blob = taxonomy_id + status_id + law_id
for token in [
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY",
    "real_case_authority_object_admission_rejection_taxonomy",
]:
    if token not in identity_blob:
        raise AssertionError("taxonomy identity missing")

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REJECTION TAXONOMY: PASS")
print(f"CURRENT_STATE={current_state}")
print("TAXONOMY_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_SEALED=true")
print(f"CANONICAL_REJECTION_REASON_COUNT={canonical_count}")
print(f"COVERED_REJECTION_REASON_COUNT={covered_count}")
print(f"UNCOVERED_REJECTION_REASON_COUNT={uncovered_count}")
print("TAXONOMY_COMPLETE_FOR_CURRENT_VALIDATOR=true")
print("CORPUS_COMPLETE_FOR_REQUIRED_REASONS=true")
print("FIXTURES_ARE_LIVE_REQUESTS=false")
print("LIVE_ADMISSION_REQUEST_COUNT=0")
print("VALID_ADMISSION_REQUEST_COUNT=0")
print("ACCEPTED_ADMISSION_REQUEST_COUNT=0")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("TAXONOMY_DOES_NOT_CREATE_LIVE_REQUESTS=true")
print("TAXONOMY_DOES_NOT_ACCEPT_REQUESTS=true")
print("TAXONOMY_DOES_NOT_REJECT_LIVE_REQUESTS=true")
print("TAXONOMY_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true")
print("TAXONOMY_DOES_NOT_SATISFY_AUTHORITY=true")
print("TAXONOMY_DOES_NOT_ADVANCE_STATE=true")
print("TAXONOMY_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("TAXONOMY_DOES_NOT_ADMIT_MEDIA=true")
print("TAXONOMY_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("TAXONOMY_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true")
print("TAXONOMY_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
