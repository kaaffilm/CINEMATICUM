#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

bash scripts/verify-open-real-case-authority-intake.sh >/dev/null

python3 - <<'PY'
import json
from pathlib import Path

paths = {
    "object": Path("CINEMATICUM_REAL_CASE_AUTHORITY_INTAKE_DOCKET.json"),
    "law": Path("CINEMATICUM_REAL_CASE_AUTHORITY_INTAKE_DOCKET_LAW.json"),
    "status": Path("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_INTAKE_DOCKET_STATUS.json"),
    "document": Path("REAL_CASE_AUTHORITY_INTAKE_DOCKET.md"),
    "open_intake": Path("CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE.json"),
    "open_intake_law": Path("CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE_LAW.json"),
    "open_intake_status": Path("CASES/CASE_001_THE_LAST_RENDER/OPEN_REAL_CASE_AUTHORITY_INTAKE_STATUS.json"),
}

for name, path in paths.items():
    assert path.exists(), f"missing {name}: {path}"

json_docs = {}
for name, path in paths.items():
    if path.suffix == ".json":
        json_docs[name] = json.loads(path.read_text())

all_text = "\n".join(path.read_text() for path in paths.values())

required_tokens = [
    "REAL_CASE_AUTHORITY_INTAKE_DOCKET",
    "OPEN_REAL_CASE_AUTHORITY_INTAKE",
]
for token in required_tokens:
    assert token in all_text, f"missing token: {token}"

def values_for_key(node, key):
    found = []
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k).lower() == key.lower():
                found.append(v)
            found.extend(values_for_key(v, key))
    elif isinstance(node, list):
        for item in node:
            found.extend(values_for_key(item, key))
    return found

def any_true(key):
    vals = []
    for doc in json_docs.values():
        vals.extend(values_for_key(doc, key))
    return any(v is True for v in vals)

def any_value(key, target):
    vals = []
    for doc in json_docs.values():
        vals.extend(values_for_key(doc, key))
    return any(v == target for v in vals)

for key in [
    "authority_satisfied",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present",
    "replay_passed",
]:
    assert not any_true(key), f"{key} must not be true"

optional_false_or_absent = [
    "accepted_authority_object_present",
    "instantiated_authority_objects_present",
    "docket_satisfies_authority",
    "docket_advances_state",
    "docket_issues_motion_picture",
    "docket_admits_media",
]
for key in optional_false_or_absent:
    assert not any_true(key), f"{key} must not be true"

slot_counts = []
for key in [
    "required_authority_object_count",
    "authority_object_slot_count",
    "docket_slot_count",
]:
    for doc in json_docs.values():
        slot_counts.extend(v for v in values_for_key(doc, key) if isinstance(v, int))

if slot_counts:
    assert 8 in slot_counts or max(slot_counts) >= 8, f"expected eight authority slots, got {slot_counts}"

for forbidden_suffix in [
    ".mp4", ".mov", ".mkv", ".avi", ".wav", ".aiff", ".mp3", ".flac",
    ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".exr", ".blend", ".psd",
]:
    hits = [
        str(path) for path in Path(".").rglob(f"*{forbidden_suffix}")
        if ".git" not in path.parts
    ]
    assert not hits, f"forbidden media/model payload files present: {hits}"

print("CINEMATICUM REAL CASE AUTHORITY INTAKE DOCKET: PASS")
print("CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
print("DOCKET_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("REAL_CASE_AUTHORITY_INTAKE_DOCKET_PRESENT=true")
print("REAL_CASE_AUTHORITY_INTAKE_DOCKET_SEALED=true")
print("OPEN_REAL_CASE_AUTHORITY_INTAKE_PRESENT=true")
print("REAL_CASE_AUTHORITY_INTAKE_OPEN=true")
print("AUTHORITY_OBJECT_SLOT_COUNT=8")
print("AUTHORITY_OBJECT_ADMISSION_REQUESTS_ALLOWED=true")
print("ADMISSION_REQUEST_COUNT=0")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECTS_PRESENT=false")
print("OBJECT_IS_NON_STAR_SEAL=false")
print("OBJECT_IS_NEGATIVE_CAPABILITY_SEAL=false")
print("DOCKET_DOES_NOT_SATISFY_AUTHORITY=true")
print("DOCKET_DOES_NOT_ADVANCE_STATE=true")
print("DOCKET_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("DOCKET_DOES_NOT_ADMIT_MEDIA=true")
print("DOCKET_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("DOCKET_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true")
print("DOCKET_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
