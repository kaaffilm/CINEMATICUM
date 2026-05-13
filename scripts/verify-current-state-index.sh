#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path.cwd()

CASE_ID = "CASE_001_THE_LAST_RENDER"
STATE = "ISSUED_ADMISSIBLE_MOTION_PICTURE"

def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

assert index["surface_type"] == "ACTIVE_CURRENT_STATE"
assert index["active_case_states"][CASE_ID] == STATE
assert index.get("active_current_state") == STATE
assert CASE_ID in index.get("release_candidate_ready_cases", [])
assert index.get("issued_films", []) == [CASE_ID]
assert index.get("media_admitted_cases", []) == [CASE_ID]

assert case["surface_type"] == "ACTIVE_CURRENT_STATE"
assert case["current_state"] == STATE
assert case["release_candidate_ready"] is True
assert case["issued"] is True
assert case["media_present"] is True
assert case["outsider_replay_passed"] is True

active = []
for path in (ROOT / "CASES").rglob("*.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("case_id") == CASE_ID and data.get("surface_type") == "ACTIVE_CURRENT_STATE":
        active.append(str(path.relative_to(ROOT)))

assert active == ["CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"], active

print("CINEMATICUM CURRENT STATE INDEX: PASS")
print(f"CASE_001=THE_LAST_RENDER")
print(f"ACTIVE_CURRENT_STATE={STATE}")
print("RELEASE_CANDIDATE_READY=true")
print("ISSUED=true")
print("MEDIA_PRESENT=true")
print("REPLAY_PASSED=true")
print("ONE_ACTIVE_CASE_STATE=true")
PY
