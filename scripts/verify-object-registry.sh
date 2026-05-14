#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
TARGET = "ISSUED_ADMISSIBLE_MOTION_PICTURE"
ISSUED_OBJECT = "HASH_BOUND_MOTION_PICTURE_MEDIA"

def load(path):
    return json.loads(Path(path).read_text())

registry = load("CINEMATICUM_OBJECT_REGISTRY.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
act = load("MOTION_PICTURE_ISSUANCE_ACT.json")
media = load("records/motion_picture_issuance/MOTION_PICTURE_MEDIA_ADMISSION_RECORD.json")

def require(cond, msg):
    if not cond:
        raise AssertionError(msg)

active = index["active_case_states"][CASE_ID]

require(active == TARGET, f"index.active_case_states[{CASE_ID}]={active!r}")
require(case["current_state"] == TARGET, f"case.current_state={case.get('current_state')!r}")
require(case["issued"] is True, "case.issued is not true")
require(case["media_present"] is True, "case.media_present is not true")
require(case["issued_object"] == ISSUED_OBJECT, f"case.issued_object={case.get('issued_object')!r}")

require(seal["current_state"] == TARGET, f"seal.current_state={seal.get('current_state')!r}")
require(seal["issued"] is True, "seal.issued is not true")
require(seal["media_present"] is True, "seal.media_present is not true")
require(seal["issued_object"] == ISSUED_OBJECT, f"seal.issued_object={seal.get('issued_object')!r}")
require(seal["raw_media_stored_in_git"] is False, "seal.raw_media_stored_in_git is not false")

require(act["issued"] is True, "act.issued is not true")
require(act["media_present"] is True, "act.media_present is not true")
require(act["issued_object"] == ISSUED_OBJECT, f"act.issued_object={act.get('issued_object')!r}")

require(media["issued"] is True, "media.issued is not true")
require(media["media_present"] is True, "media.media_present is not true")
require(media["issued_object"] == ISSUED_OBJECT, f"media.issued_object={media.get('issued_object')!r}")

# Registry may contain historical objects, but its active summary must not contradict the truth owners.
for key in ["active_current_state", "current_active_state", "current_state", "active_state"]:
    if key in registry:
        require(registry[key] == TARGET, f"registry.{key}={registry[key]!r}")

for key in ["issued", "media_present"]:
    if key in registry:
        require(registry[key] is True, f"registry.{key}={registry[key]!r}")

if "issued_object" in registry:
    require(registry["issued_object"] == ISSUED_OBJECT, f"registry.issued_object={registry['issued_object']!r}")

if "active_case_states" in registry:
    require(registry["active_case_states"][CASE_ID] == TARGET, f"registry.active_case_states[{CASE_ID}]={registry['active_case_states'][CASE_ID]!r}")

registered_objects = len(registry.get("objects", registry.get("registered_objects", [])))

print("CINEMATICUM OBJECT REGISTRY: PASS")
print(f"REGISTERED_OBJECTS={registered_objects}")
print(f"ACTIVE_CURRENT_STATE={TARGET}")
print("ONE_ACTIVE_CASE_STATE=true")
print("ISSUED=true")
print("MEDIA_PRESENT=true")
print(f"ISSUED_OBJECT={ISSUED_OBJECT}")
PY
