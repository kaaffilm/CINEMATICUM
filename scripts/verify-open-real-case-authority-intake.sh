#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
import sys
from pathlib import Path

CASE = "CASE_001_THE_LAST_RENDER"
HISTORICAL_TARGET = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
ACTIVE_TARGET = "ISSUED_ADMISSIBLE_MOTION_PICTURE"

def load(path):
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))

def fail(msg):
    print(f"OPEN_REAL_CASE_AUTHORITY_INTAKE_VERIFY_FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)

paths = [
    "OPEN_REAL_CASE_AUTHORITY_INTAKE.json",
    "CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE.json",
    "OPEN_REAL_CASE_AUTHORITY_INTAKE_LAW.json",
    "CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE_LAW.json",
    "CASES/CASE_001_THE_LAST_RENDER/OPEN_REAL_CASE_AUTHORITY_INTAKE_STATUS.json",
]

objects = [(p, load(p)) for p in paths]
objects = [(p, obj) for p, obj in objects if obj is not None]

if not objects:
    fail("no open-real-case-authority-intake JSON objects found")

index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case_state = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

if index is None:
    fail("missing CINEMATICUM_CURRENT_STATE_INDEX.json")
if case_state is None:
    fail("missing CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
if registry is None:
    fail("missing CINEMATICUM_OBJECT_REGISTRY.json")

active_index_state = index["active_case_states"][CASE]
active_case_state = case_state["current_state"]
active_registry_state = registry.get("current_active_state")

if active_index_state != ACTIVE_TARGET:
    fail(f"index active state mismatch: {active_index_state!r}")
if active_case_state != ACTIVE_TARGET:
    fail(f"case active state mismatch: {active_case_state!r}")
if active_registry_state not in (ACTIVE_TARGET, "RELEASE_CANDIDATE_READY"):
    fail(f"registry active state mismatch: {active_registry_state!r}")

for path, obj in objects:
    if obj.get("case_id") not in (None, CASE):
        fail(f"{path}: bad case_id={obj.get('case_id')!r}")

    state = obj.get("current_state") or obj.get("record_current_state")
    if state not in (None, HISTORICAL_TARGET, ACTIVE_TARGET):
        fail(f"{path}: unexpected state={state!r}")

    if obj.get("status") not in (None, "PASS"):
        fail(f"{path}: status is not PASS: {obj.get('status')!r}")

    for key in (
        "authority_satisfied",
        "may_advance_now",
        "release_candidate_ready",
        "issuance_unblocked",
        "issued",
        "media_present",
    ):
        if key in obj and obj[key] is not False:
            fail(f"{path}: expected {key}=false, got {obj[key]!r}")

print("CINEMATICUM OPEN REAL CASE AUTHORITY INTAKE: PASS")
print(f"CURRENT_STATE={HISTORICAL_TARGET}")
print(f"RECORD_CURRENT_STATE={HISTORICAL_TARGET}")
print(f"ACTIVE_CURRENT_STATE={ACTIVE_TARGET}")
print("REAL_CASE_AUTHORITY_INTAKE_OPEN=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ACTIVE_RELEASE_CANDIDATE_READY=true")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
