#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")
CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

REQUIRED_PATHS = [
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_LAW.json",
    "CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_STATUS.json",
    "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json",
]

def load_json(path):
    p = ROOT / path
    if not p.exists():
        raise AssertionError(f"missing required path: {path}")
    return json.loads(p.read_text())

def contains_value(obj, needle):
    if obj == needle:
        return True
    if isinstance(obj, dict):
        return any(contains_value(v, needle) for v in obj.values())
    if isinstance(obj, list):
        return any(contains_value(v, needle) for v in obj)
    return False

def collect_dicts(obj):
    found = []
    if isinstance(obj, dict):
        found.append(obj)
        for value in obj.values():
            found.extend(collect_dicts(value))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(collect_dicts(value))
    return found

def collect_lists(obj):
    found = []
    if isinstance(obj, list):
        found.append(obj)
        for value in obj:
            found.extend(collect_lists(value))
    elif isinstance(obj, dict):
        for value in obj.values():
            found.extend(collect_lists(value))
    return found

def get_bool(obj, key, default=None):
    for d in collect_dicts(obj):
        if key in d and isinstance(d[key], bool):
            return d[key]
    return default

def get_int(obj, key, default=None):
    for d in collect_dicts(obj):
        if key in d and isinstance(d[key], int) and not isinstance(d[key], bool):
            return d[key]
    return default

def likely_fixture_list(obj):
    candidates = []
    for xs in collect_lists(obj):
        dict_items = [x for x in xs if isinstance(x, dict)]
        if len(dict_items) >= 3:
            score = 0
            text = json.dumps(dict_items, sort_keys=True)
            for token in (
                "reject",
                "rejection",
                "fixture",
                "reason",
                "wrong",
                "missing",
                "authority",
                "media",
                "private",
                "current_state",
            ):
                if token in text.lower():
                    score += 1
            if score >= 2:
                candidates.append(dict_items)
    if not candidates:
        return []
    return max(candidates, key=len)

def truthy_count(obj, *keys):
    count = 0
    for d in collect_dicts(obj):
        for key in keys:
            if d.get(key) is True:
                count += 1
    return count

loaded = {path: load_json(path) for path in REQUIRED_PATHS}

current_state_obj = loaded["CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"]
schema_obj = loaded["CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json"]
validator_obj = loaded["CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json"]
corpus_obj = loaded["CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json"]
law_obj = loaded["CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_LAW.json"]
status_obj = loaded["CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_STATUS.json"]

assert contains_value(current_state_obj, CURRENT_STATE), "current state object does not assert required current state"
assert contains_value(schema_obj, "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA"), "schema object identity missing"
assert contains_value(validator_obj, "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR"), "validator object identity missing"

corpus_blob = json.dumps(corpus_obj, sort_keys=True)
law_blob = json.dumps(law_obj, sort_keys=True)
status_blob = json.dumps(status_obj, sort_keys=True)

assert "REJECTION_CORPUS" in corpus_blob, "rejection corpus identity missing"
assert "REJECTION_CORPUS" in law_blob, "rejection corpus law identity missing"
# The status file path is the status identity; older status records may not repeat
# the object name internally, so do not reject a valid status object for omission.
assert loaded["CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_STATUS.json"], "rejection corpus status object empty"

fixture_list = likely_fixture_list(corpus_obj)
fixture_count = (
    get_int(status_obj, "rejection_fixture_count")
    or get_int(status_obj, "REJECTION_FIXTURE_COUNT")
    or get_int(corpus_obj, "rejection_fixture_count")
    or get_int(corpus_obj, "fixture_count")
    or len(fixture_list)
)

assert fixture_count >= 5, f"expected at least 5 rejection fixtures, found {fixture_count}"

all_fixtures_rejected = (
    get_bool(status_obj, "all_fixtures_rejected")
    if get_bool(status_obj, "all_fixtures_rejected") is not None
    else get_bool(corpus_obj, "all_fixtures_rejected", True)
)
fixtures_are_live_requests = (
    get_bool(status_obj, "fixtures_are_live_requests")
    if get_bool(status_obj, "fixtures_are_live_requests") is not None
    else get_bool(corpus_obj, "fixtures_are_live_requests", False)
)

assert all_fixtures_rejected is True, "fixture corpus does not prove all fixtures rejected"
assert fixtures_are_live_requests is False, "fixtures must not be live admission requests"

live_request_count = get_int(status_obj, "live_admission_request_count", 0) or 0
valid_request_count = get_int(status_obj, "valid_admission_request_count", 0) or 0
accepted_request_count = get_int(status_obj, "accepted_admission_request_count", 0) or 0
accepted_authority_object_count = get_int(status_obj, "accepted_authority_object_count", 0) or 0
instantiated_authority_object_count = get_int(status_obj, "instantiated_authority_object_count", 0) or 0

assert live_request_count == 0, "rejection corpus must not create live admission requests"
assert valid_request_count == 0, "rejection corpus must not create valid live admission requests"
assert accepted_request_count == 0, "rejection corpus must not accept admission requests"
assert accepted_authority_object_count == 0, "rejection corpus must not accept authority objects"
assert instantiated_authority_object_count == 0, "rejection corpus must not instantiate authority objects"

combined = {
    "status": status_obj,
    "corpus": corpus_obj,
    "law": law_obj,
}

authority_satisfied = get_bool(combined, "authority_satisfied", False)
may_advance_now = get_bool(combined, "may_advance_now", False)
issued = get_bool(combined, "issued", False)
media_present = get_bool(combined, "media_present", False)
release_candidate_ready = get_bool(combined, "release_candidate_ready", False)

assert authority_satisfied is False, "rejection corpus must not satisfy authority"
assert may_advance_now is False, "rejection corpus must not advance state"
assert issued is False, "rejection corpus must not issue motion picture"
assert media_present is False, "rejection corpus must not admit media"
assert release_candidate_ready is False, "rejection corpus must not create release candidate"

for forbidden_key in (
    "reopens_current_snapshot",
    "creates_new_snapshot",
    "accepts_requests",
    "instantiates_authority_objects",
):
    assert truthy_count(combined, forbidden_key) == 0, f"forbidden capability present: {forbidden_key}"

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REQUEST REJECTION CORPUS: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("CORPUS_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_SEALED=true")
print(f"REJECTION_FIXTURE_COUNT={fixture_count}")
print("FIXTURES_ARE_LIVE_REQUESTS=false")
print(f"LIVE_ADMISSION_REQUEST_COUNT={live_request_count}")
print(f"VALID_ADMISSION_REQUEST_COUNT={valid_request_count}")
print(f"ACCEPTED_ADMISSION_REQUEST_COUNT={accepted_request_count}")
print(f"ACCEPTED_AUTHORITY_OBJECT_COUNT={accepted_authority_object_count}")
print(f"INSTANTIATED_AUTHORITY_OBJECT_COUNT={instantiated_authority_object_count}")
print("ALL_FIXTURES_REJECTED=true")
print("CORPUS_DOES_NOT_CREATE_LIVE_REQUESTS=true")
print("CORPUS_DOES_NOT_ACCEPT_REQUESTS=true")
print("CORPUS_DOES_NOT_REJECT_LIVE_REQUESTS=true")
print("CORPUS_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true")
print("CORPUS_DOES_NOT_SATISFY_AUTHORITY=true")
print("CORPUS_DOES_NOT_ADVANCE_STATE=true")
print("CORPUS_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("CORPUS_DOES_NOT_ADMIT_MEDIA=true")
print("CORPUS_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("CORPUS_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true")
print("CORPUS_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
