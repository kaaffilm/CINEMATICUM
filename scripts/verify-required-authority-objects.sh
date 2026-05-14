#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
RECORD_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
ACTIVE_STATE = "RELEASE_CANDIDATE_READY"

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def maybe_load(path):
    p = Path(path)
    return load(path) if p.exists() else None

root = maybe_load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECTS.json")
law = maybe_load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECTS_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/REQUIRED_AUTHORITY_OBJECTS_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

objects = [obj for obj in (root, law, status) if obj is not None]

for obj in objects:
    if "case_id" in obj:
        assert obj["case_id"] == CASE_ID
    if "current_state" in obj:
        assert obj["current_state"] == RECORD_STATE, obj["current_state"]
    if "required_authority_objects_missing" in obj:
        assert obj["required_authority_objects_missing"] is False
    if "authority_object_stack_complete" in obj:
        assert obj["authority_object_stack_complete"] is True
    if "accepted_authority_object_count" in obj:
        assert obj["accepted_authority_object_count"] == 8
    if "instantiated_authority_object_count" in obj:
        assert obj["instantiated_authority_object_count"] == 8
    if "unfilled_authority_object_slot_count" in obj:
        assert obj["unfilled_authority_object_slot_count"] == 0
    if "may_advance_now" in obj:
        assert obj["may_advance_now"] is False
    if "issuance_unblocked" in obj:
        assert obj["issuance_unblocked"] is False
    if "issued" in obj:
        assert obj["issued"] is False
    if "media_present" in obj:
        assert obj["media_present"] is False

assert index["active_case_states"][CASE_ID] == ACTIVE_STATE
assert index["active_current_state"] == ACTIVE_STATE
assert case["current_state"] == ACTIVE_STATE
assert case["release_candidate_ready"] is True
assert case["issued"] is False, case["issued"]
assert case["media_present"] is False, case["media_present"]

print("CINEMATICUM REQUIRED AUTHORITY OBJECT CHECKLIST: PASS")
print(f"RECORD_CURRENT_STATE={RECORD_STATE}")
print(f"ACTIVE_CURRENT_STATE={ACTIVE_STATE}")
print("REQUIRED_AUTHORITY_OBJECTS_MISSING=false")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=8")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=8")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=0")
print("RELEASE_CANDIDATE_READY=true")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
