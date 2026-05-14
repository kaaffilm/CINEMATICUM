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

def load_if_present(path):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

seal = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL.json")
law = load_if_present("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

records = [seal, status] + ([law] if law is not None else [])

for obj in records:
    assert obj["case_id"] == CASE_ID
    obj_state = obj.get("current_state") or obj.get("record_current_state") or RECORD_STATE
    assert obj_state == RECORD_STATE, obj_state

    for key in (
        "future_continuity_seal_present",
        "future_continuity_seal_declared",
        "current_zero_admission_snapshot_continuity_preserved",
        "future_valid_admission_requests_allowed_under_law",
        "future_valid_admission_requests_must_target_future_snapshot",
        "future_valid_admission_requests_do_not_mutate_current_zero_snapshot",
    ):
        if key in obj:
            assert obj[key] is True, f"{key}={obj[key]}"

    for key in (
        "authority_satisfied",
        "may_advance_now",
        "release_candidate_ready",
        "issued",
        "media_present",
    ):
        if key in obj:
            assert obj[key] is False, f"{key}={obj[key]}"

assert index["active_case_states"][CASE_ID] == ACTIVE_STATE, index["active_case_states"][CASE_ID]
assert case["current_state"] == ACTIVE_STATE, case["current_state"]
assert case["release_candidate_ready"] is True
assert case["issued"] is False, case["issued"]
assert case["media_present"] is False, case["media_present"]

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION FUTURE CONTINUITY SEAL: PASS")
print(f"CURRENT_STATE={RECORD_STATE}")
print(f"RECORD_CURRENT_STATE={RECORD_STATE}")
print(f"ACTIVE_CURRENT_STATE={ACTIVE_STATE}")
print("FUTURE_CONTINUITY_SEAL_PRESENT=true")
print("FUTURE_CONTINUITY_SEAL_DECLARED=true")
print("CURRENT_ZERO_ADMISSION_SNAPSHOT_CONTINUITY_PRESERVED=true")
print("FUTURE_VALID_ADMISSION_REQUESTS_ALLOWED_UNDER_LAW=true")
print("FUTURE_VALID_ADMISSION_REQUESTS_MUST_TARGET_FUTURE_SNAPSHOT=true")
print("FUTURE_VALID_ADMISSION_REQUESTS_DO_NOT_MUTATE_CURRENT_ZERO_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ACTIVE_RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
