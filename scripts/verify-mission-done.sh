#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
STATE = "ISSUED_ADMISSIBLE_MOTION_PICTURE"
ISSUED_OBJECT = "HASH_BOUND_MOTION_PICTURE_MEDIA"

def load(path):
    return json.loads(Path(path).read_text())

def require(cond, msg):
    if not cond:
        raise AssertionError(msg)

index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
repo = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
act = load("MOTION_PICTURE_ISSUANCE_ACT.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/MOTION_PICTURE_ISSUANCE_ACT_STATUS.json")
record = load("records/motion_picture_issuance/MOTION_PICTURE_MEDIA_ADMISSION_RECORD.json")

active = index.get("active_case_states", {}).get(CASE_ID)
require(active == STATE, f"active_case_states[{CASE_ID}]={active!r}")

for label, obj in {
    "current_case": case,
    "repository_status": repo,
    "motion_picture_issuance_act": act,
    "motion_picture_issuance_act_status": status,
    "media_admission_record": record,
}.items():
    require(obj.get("issued") is True, f"{label}.issued={obj.get('issued')!r}")
    require(obj.get("media_present") is True, f"{label}.media_present={obj.get('media_present')!r}")

for label, obj in {
    "current_case": case,
    "repository_status": repo,
    "motion_picture_issuance_act": act,
    "motion_picture_issuance_act_status": status,
}.items():
    require(obj.get("issued_object") == ISSUED_OBJECT, f"{label}.issued_object={obj.get('issued_object')!r}")

require(repo.get("raw_media_stored_in_git") is False, f"repository_status.raw_media_stored_in_git={repo.get('raw_media_stored_in_git')!r}")
require(record.get("raw_media_stored_in_git") is False, f"media_admission_record.raw_media_stored_in_git={record.get('raw_media_stored_in_git')!r}")

print("MISSION_DONE=true")
print(f"CASE_ID={CASE_ID}")
print(f"ACTIVE_CURRENT_STATE={STATE}")
print("ISSUED=true")
print("MEDIA_PRESENT=true")
print(f"ISSUED_OBJECT={ISSUED_OBJECT}")
print("RAW_MEDIA_STORED_IN_GIT=false")
PY
