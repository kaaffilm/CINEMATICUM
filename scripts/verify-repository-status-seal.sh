#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path.cwd()

def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")

active = index["active_case_states"]["CASE_001_THE_LAST_RENDER"]

assert seal["surface_type"] == "REPOSITORY_STATUS_SEAL"
assert seal["current_state"] == active
assert seal["current_state"] == "RELEASE_CANDIDATE_READY"

assert seal["release_candidate_ready"] is True
assert seal["issued"] is False
assert seal["media_present"] is False
assert seal.get("replay_passed", False) is False

assert index["active_current_state"] == "RELEASE_CANDIDATE_READY"
assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == "RELEASE_CANDIDATE_READY"

print("CINEMATICUM REPOSITORY STATUS SEAL: PASS")
print(f"ACTIVE_CURRENT_STATE={seal['current_state']}")
print(f"RELEASE_CANDIDATE_READY={str(seal['release_candidate_ready']).lower()}")
print(f"ISSUED={str(seal['issued']).lower()}")
print(f"MEDIA_PRESENT={str(seal['media_present']).lower()}")
print(f"REPLAY_PASSED={str(seal.get('replay_passed', False)).lower()}")
print("VERIFY_ALL_REQUIRED=true")
print("REGISTRY_FRESH_REQUIRED=true")
PY
