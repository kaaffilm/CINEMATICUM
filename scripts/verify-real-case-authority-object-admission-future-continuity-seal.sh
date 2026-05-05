#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")
CASE = ROOT / "CASES" / "CASE_001_THE_LAST_RENDER"

def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def dotted(data, path):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(path)
        cur = cur[part]
    return cur

def recursive_find(data, key):
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            try:
                return recursive_find(value, key)
            except KeyError:
                pass
    elif isinstance(data, list):
        for value in data:
            try:
                return recursive_find(value, key)
            except KeyError:
                pass
    raise KeyError(key)

def pick(data, *paths_or_keys):
    for item in paths_or_keys:
        try:
            if "." in item:
                return dotted(data, item)
            return recursive_find(data, item)
        except KeyError:
            pass
    raise KeyError(paths_or_keys)

state = load(CASE / "CURRENT_CASE_STATE.json")
permanence = load(ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_PERMANENCE_SEAL.json")
slot_index = load(ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX.json")
obj = load(ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL.json")
law = load(ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL_LAW.json")
status = load(CASE / "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL_STATUS.json")

assert state["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert obj["object_type"] == "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL"
assert law["object_type"] == "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL_LAW"
assert status["future_continuity_sealed"] is True

assert pick(
    permanence,
    "current_zero_admission_snapshot_permanent",
    "current_zero_snapshot.permanent",
    "status.current_zero_admission_snapshot_permanent"
) is True

assert pick(
    permanence,
    "current_zero_admission_snapshot_mutable",
    "current_zero_snapshot.mutable",
    "status.current_zero_admission_snapshot_mutable"
) is False

assert pick(
    permanence,
    "current_zero_admission_snapshot_terminal",
    "current_zero_snapshot.terminal",
    "status.current_zero_admission_snapshot_terminal"
) is True

cz = obj["current_zero_snapshot"]
assert cz["final"] is True
assert cz["terminal"] is True
assert cz["permanent"] is True
assert cz["mutable"] is False
assert cz["closed_against_reclassification"] is True

future = obj["future_admission_request_law"]
for key in [
    "future_valid_admission_requests_allowed_under_law",
    "future_valid_admission_requests_require_explicit_request",
    "future_valid_admission_requests_require_validation",
    "future_valid_admission_requests_require_decision",
    "future_valid_admission_requests_require_enforcement_gate",
    "future_valid_admission_requests_must_target_future_snapshot",
    "future_valid_admission_requests_create_new_snapshot",
    "future_valid_admission_requests_do_not_mutate_current_zero_snapshot",
    "future_valid_admission_requests_do_not_mutate_terminal_snapshot",
    "future_valid_admission_requests_do_not_convert_zero_snapshot_into_authority",
]:
    assert future[key] is True, key

route = obj["authority_slot_route"]
assert route["authority_object_slot_count"] == 8
assert route["accepted_authority_object_count_now"] == 0
assert route["instantiated_authority_object_count_now"] == 0
assert route["first_future_authority_slot_candidate"] == "DIRECTOR_ACCEPTANCE_OBJECT"
assert route["slot_filling_allowed_only_in_future_snapshot"] is True

slot_count = (
    slot_index.get("authority_object_slot_count")
    or slot_index.get("authority_object_slots_count")
    or slot_index.get("slot_count")
    or slot_index.get("slot_index", {}).get("authority_object_slot_count")
    or slot_index.get("status", {}).get("authority_object_slot_count")
    or pick(slot_index, "authority_object_slot_count")
)
assert slot_count == 8

for key, value in obj["non_effects"].items():
    assert value is True, key

for key in [
    "authority_satisfied",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present",
]:
    assert obj["status"][key] is False, key
    assert status[key] is False, key

assert law["law"]["forbids_current_zero_mutation"] is True
assert law["law"]["forbids_terminal_snapshot_mutation"] is True
assert law["law"]["forbids_silent_slot_filling"] is True
assert law["law"]["requires_future_snapshot_for_valid_admission"] is True

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION FUTURE CONTINUITY SEAL: PASS")
print(f"CURRENT_STATE={state['current_state']}")
print(f"CONTINUITY_SCOPE={obj['seal_scope']}")
print(f"CURRENT_ZERO_ADMISSION_SNAPSHOT_PERMANENT={cz['permanent']}")
print(f"CURRENT_ZERO_ADMISSION_SNAPSHOT_MUTABLE={cz['mutable']}")
print(f"FUTURE_VALID_ADMISSION_REQUESTS_ALLOWED_UNDER_LAW={future['future_valid_admission_requests_allowed_under_law']}")
print(f"FUTURE_VALID_ADMISSION_REQUESTS_MUST_TARGET_FUTURE_SNAPSHOT={future['future_valid_admission_requests_must_target_future_snapshot']}")
print(f"FUTURE_VALID_ADMISSION_REQUESTS_CREATE_NEW_SNAPSHOT={future['future_valid_admission_requests_create_new_snapshot']}")
print(f"FUTURE_VALID_ADMISSION_REQUESTS_DO_NOT_MUTATE_CURRENT_ZERO_SNAPSHOT={future['future_valid_admission_requests_do_not_mutate_current_zero_snapshot']}")
print(f"FUTURE_VALID_ADMISSION_REQUESTS_DO_NOT_MUTATE_TERMINAL_SNAPSHOT={future['future_valid_admission_requests_do_not_mutate_terminal_snapshot']}")
print(f"AUTHORITY_OBJECT_SLOT_COUNT={route['authority_object_slot_count']}")
print(f"FIRST_FUTURE_AUTHORITY_SLOT_CANDIDATE={route['first_future_authority_slot_candidate']}")
print(f"ACCEPTED_AUTHORITY_OBJECT_COUNT_NOW={route['accepted_authority_object_count_now']}")
print(f"INSTANTIATED_AUTHORITY_OBJECT_COUNT_NOW={route['instantiated_authority_object_count_now']}")
print(f"AUTHORITY_SATISFIED={obj['status']['authority_satisfied']}")
print(f"MAY_ADVANCE_NOW={obj['status']['may_advance_now']}")
print(f"RELEASE_CANDIDATE_READY={obj['status']['release_candidate_ready']}")
print(f"ISSUED={obj['status']['issued']}")
print(f"MEDIA_PRESENT={obj['status']['media_present']}")
PY
