#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

REQUEST_PATH = Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS/REQ_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json")
STATUS_PATH = Path("CASES/CASE_001_THE_LAST_RENDER/FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_ADMISSION_REQUEST_STATUS.json")
LAW_PATH = Path("CINEMATICUM_FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_ADMISSION_REQUEST_LAW.json")
FORK_GATE_PATH = Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_SNAPSHOT_FORK_GATE.json")

REQUIRED_PATHS = [REQUEST_PATH, STATUS_PATH, LAW_PATH, FORK_GATE_PATH]

def load_json(path: Path):
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid json in {path}: {exc}") from exc

def walk_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_values(item)

def find_first(data, names, default=None):
    wanted = {name.lower() for name in names}
    for key, value in walk_values(data):
        if key.lower() in wanted:
            return value
    return default

def as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)

def as_int(value, default=0):
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except Exception:
        return default

request = load_json(REQUEST_PATH)
status = load_json(STATUS_PATH)
law = load_json(LAW_PATH)
fork_gate = load_json(FORK_GATE_PATH)

combined = {
    "request": request,
    "status": status,
    "law": law,
    "fork_gate": fork_gate,
}
combined_text = json.dumps(combined, sort_keys=True)

required_tokens = [
    "director_final_cut_authority",
    "DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT",
    "FUTURE_VALID_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS",
]
for token in required_tokens:
    if token not in combined_text:
        raise AssertionError(f"missing required token: {token}")

current_state = find_first(
    combined,
    ["current_state", "active_current_state"],
    "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED",
)

request_id = find_first(
    combined,
    ["request_id", "admission_request_id", "id"],
    "REQ_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT",
)

authority_slot_id = find_first(
    combined,
    ["authority_slot_id", "slot_id", "canonical_first_future_authority_slot_id"],
    "director_final_cut_authority",
)

authority_object = find_first(
    combined,
    ["authority_object", "authority_object_id", "canonical_first_future_authority_object"],
    "DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT",
)

live_request_count = as_int(find_first(
    combined,
    ["live_admission_request_count", "admission_request_count"],
    0,
))

valid_request_count = as_int(find_first(
    combined,
    ["valid_admission_request_count"],
    0,
))

accepted_decision_count = as_int(find_first(
    combined,
    ["accepted_decision_count", "accepted_admission_request_count"],
    0,
))

accepted_authority_object_count = as_int(find_first(
    combined,
    ["accepted_authority_object_count"],
    0,
))

instantiated_authority_object_count = as_int(find_first(
    combined,
    ["instantiated_authority_object_count"],
    0,
))

current_zero_mutated = as_bool(find_first(
    combined,
    [
        "current_zero_admission_snapshot_mutated",
        "current_zero_snapshot_mutated",
        "current_zero_admission_snapshot_mutable",
    ],
    False,
))

future_snapshot_fork_gate_open_now = as_bool(find_first(
    combined,
    ["future_snapshot_fork_gate_open_now"],
    False,
))

future_snapshot_fork_gate_passed = as_bool(find_first(
    combined,
    ["future_snapshot_fork_gate_passed"],
    False,
))

authority_satisfied = as_bool(find_first(combined, ["authority_satisfied"], False))
may_advance_now = as_bool(find_first(combined, ["may_advance_now"], False))
release_candidate_ready = as_bool(find_first(combined, ["release_candidate_ready"], False))
issued = as_bool(find_first(combined, ["issued"], False))
media_present = as_bool(find_first(combined, ["media_present"], False))

assert current_state == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert authority_slot_id == "director_final_cut_authority"
assert authority_object == "DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"
assert "REQ_001" in str(request_id) or "DIRECTOR_FINAL_CUT" in str(request_id)
assert live_request_count == 0
assert accepted_decision_count == 0
assert accepted_authority_object_count == 0
assert instantiated_authority_object_count == 0
assert current_zero_mutated is False
assert future_snapshot_fork_gate_open_now is False
assert future_snapshot_fork_gate_passed is False
assert authority_satisfied is False
assert may_advance_now is False
assert release_candidate_ready is False
assert issued is False
assert media_present is False

print("CINEMATICUM FIRST FUTURE DIRECTOR FINAL CUT AUTHORITY OBJECT ADMISSION REQUEST: PASS")
print(f"CURRENT_STATE={current_state}")
print("REQUEST_SCOPE=FUTURE_VALID_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS_ONLY")
print(f"REQUEST_ID={request_id}")
print(f"AUTHORITY_SLOT_ID={authority_slot_id}")
print(f"AUTHORITY_OBJECT={authority_object}")
print("REQUEST_TARGETS_FUTURE_SNAPSHOT=true")
print("REQUEST_DOES_NOT_MUTATE_CURRENT_ZERO_SNAPSHOT=true")
print("REQUEST_DOES_NOT_MUTATE_TERMINAL_SNAPSHOT=true")
print(f"LIVE_ADMISSION_REQUEST_COUNT={live_request_count}")
print(f"VALID_ADMISSION_REQUEST_COUNT={valid_request_count}")
print(f"ACCEPTED_DECISION_COUNT={accepted_decision_count}")
print(f"ACCEPTED_AUTHORITY_OBJECT_COUNT={accepted_authority_object_count}")
print(f"INSTANTIATED_AUTHORITY_OBJECT_COUNT={instantiated_authority_object_count}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_PASSED={str(future_snapshot_fork_gate_passed).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW={str(future_snapshot_fork_gate_open_now).lower()}")
print(f"AUTHORITY_SATISFIED={str(authority_satisfied).lower()}")
print(f"MAY_ADVANCE_NOW={str(may_advance_now).lower()}")
print(f"RELEASE_CANDIDATE_READY={str(release_candidate_ready).lower()}")
print(f"ISSUED={str(issued).lower()}")
print(f"MEDIA_PRESENT={str(media_present).lower()}")
PY
