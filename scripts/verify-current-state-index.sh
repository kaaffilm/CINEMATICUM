#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path.cwd()
CASE_ID = "CASE_001_THE_LAST_RENDER"
STATE = "RELEASE_CANDIDATE_READY"

def load(path):
    return json.loads((ROOT / path).read_text())

index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

assert index["surface_type"] == "ACTIVE_CURRENT_STATE"
assert index["active_case_states"][CASE_ID] == STATE
assert index.get("active_current_state") == STATE
assert CASE_ID in index.get("release_candidate_ready_cases", [])
assert index.get("issued_films", []) == []
assert index.get("media_admitted_cases", []) == []
assert index.get("issued") is False
assert index.get("media_present") is False

assert case["surface_type"] == "ACTIVE_CURRENT_STATE"
assert case["current_state"] == STATE
assert case["release_candidate_ready"] is True
assert case["issued"] is False
assert case["media_present"] is False
assert case.get("media_substance_passed") is False
assert case.get("blocked_by") == "MEDIA_SUBSTANCE_GATE"

active = []
for path in (ROOT / "CASES").rglob("*.json"):
    data = json.loads(path.read_text())
    if data.get("case_id") == CASE_ID and data.get("surface_type") == "ACTIVE_CURRENT_STATE":
        active.append(str(path.relative_to(ROOT)))

assert active == ["CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"], active

print("CINEMATICUM CURRENT STATE INDEX: PASS")
print("CASE_001=THE_LAST_RENDER")
print(f"ACTIVE_CURRENT_STATE={STATE}")
print("RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("MEDIA_SUBSTANCE_PASSED=false")
print("BLOCKED_BY=MEDIA_SUBSTANCE_GATE")
print("ONE_ACTIVE_CASE_STATE=true")
PY
