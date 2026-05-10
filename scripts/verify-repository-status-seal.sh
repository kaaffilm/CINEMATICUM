#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path.cwd()
seal_path = ROOT / "CINEMATICUM_REPOSITORY_STATUS_SEAL.json"

with seal_path.open(encoding="utf-8") as f:
    seal = json.load(f)

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def b(value):
    return "true" if bool(value) else "false"

require(seal.get("repository") == "kaaffilm/CINEMATICUM", seal)
require(seal.get("case_id") == "CASE_001_THE_LAST_RENDER", seal)

require(seal.get("authority_object_stack_complete") is True, seal)
require(seal.get("release_candidate_ready") is True, seal)

require(seal.get("issued") is False, seal)
require(seal.get("media_present") is False, seal)
require(seal.get("issuance_unblocked") is False, seal)

require(seal.get("admissible_motion_picture_issued") is False, seal)
require(seal.get("motion_picture_issued") is False, seal)
require(seal.get("motion_picture_media_issuance_ready") is False, seal)

print("CINEMATICUM REPOSITORY STATUS SEAL: PASS")
print(f"CURRENT_STATE={seal.get('current_state')}")
print(f"ACTIVE_CURRENT_STATE={seal.get('active_current_state')}")
print(f"AUTHORITY_OBJECT_STACK_COMPLETE={b(seal.get('authority_object_stack_complete'))}")
print(f"RELEASE_CANDIDATE_READY={b(seal.get('release_candidate_ready'))}")
print(f"MAY_ADVANCE_NOW={b(seal.get('may_advance_now'))}")
print(f"ISSUANCE_UNBLOCKED={b(seal.get('issuance_unblocked'))}")
print(f"ISSUED={b(seal.get('issued'))}")
print(f"ADMISSIBLE_MOTION_PICTURE_ISSUED={b(seal.get('admissible_motion_picture_issued'))}")
print(f"MOTION_PICTURE_ISSUED={b(seal.get('motion_picture_issued'))}")
print(f"MOTION_PICTURE_MEDIA_ISSUANCE_READY={b(seal.get('motion_picture_media_issuance_ready'))}")
print(f"MEDIA_PRESENT={b(seal.get('media_present'))}")
print(f"REGISTRY_FRESH_REQUIRED={b(seal.get('registry_fresh_required'))}")
PY
