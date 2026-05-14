#!/usr/bin/env bash
set -euo pipefail

if ! bash scripts/verify-media-substance.sh; then
  echo "MISSION_DONE=false"
  echo "BLOCKED_BY=MEDIA_SUBSTANCE_GATE"
  exit 1
fi

python3 - <<'PY'
import json
from pathlib import Path

ISSUED_STATE = "ISSUED_ADMISSIBLE_MOTION_PICTURE"
ISSUED_OBJECT = "HASH_BOUND_MOTION_PICTURE_MEDIA"

def load(path):
    return json.loads(Path(path).read_text())

index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
record = load("records/motion_picture_issuance/MOTION_PICTURE_MEDIA_ADMISSION_RECORD.json")

def require(cond, msg):
    if not cond:
        raise AssertionError(msg)

require(index.get("active_current_state") == ISSUED_STATE, f"index.active_current_state={index.get('active_current_state')!r}")
require(case.get("current_state") == ISSUED_STATE or case.get("active_current_state") == ISSUED_STATE, "case not issued state")
require(case.get("issued") is True, f"case.issued={case.get('issued')!r}")
require(case.get("media_present") is True, f"case.media_present={case.get('media_present')!r}")
require(case.get("issued_object") == ISSUED_OBJECT, f"case.issued_object={case.get('issued_object')!r}")

for name, obj in [("seal", seal), ("record", record)]:
    require(obj.get("issued") is True, f"{name}.issued={obj.get('issued')!r}")
    require(obj.get("media_present") is True, f"{name}.media_present={obj.get('media_present')!r}")
    require(obj.get("issued_object") == ISSUED_OBJECT, f"{name}.issued_object={obj.get('issued_object')!r}")
    require(obj.get("raw_media_stored_in_git") is False, f"{name}.raw_media_stored_in_git={obj.get('raw_media_stored_in_git')!r}")

print("MISSION_DONE=true")
print("CASE_ID=CASE_001_THE_LAST_RENDER")
print(f"ACTIVE_CURRENT_STATE={ISSUED_STATE}")
print("ISSUED=true")
print("MEDIA_PRESENT=true")
print(f"ISSUED_OBJECT={ISSUED_OBJECT}")
print("RAW_MEDIA_STORED_IN_GIT=false")
PY
