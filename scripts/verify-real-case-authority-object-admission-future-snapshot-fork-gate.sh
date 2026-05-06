#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")
CASE = ROOT / "CASES" / "CASE_001_THE_LAST_RENDER"

def load(path):
    path = Path(path)
    if not path.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

obj = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_SNAPSHOT_FORK_GATE.json")
law = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_SNAPSHOT_FORK_GATE_LAW.json")
status = load(CASE / "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_SNAPSHOT_FORK_GATE_STATUS.json")
continuity = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL.json")
permanence = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_PERMANENCE_SEAL.json")
slot_index = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX.json")
state = load(CASE / "CURRENT_CASE_STATE.json")

assert state["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"

assert obj["object_type"] == "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_SNAPSHOT_FORK_GATE"
assert law["object_type"] == "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_SNAPSHOT_FORK_GATE_LAW"
assert status["object_type"] == obj["object_type"]

assert continuity["status"]["future_continuity_sealed"] is True
assert continuity["current_zero_snapshot"]["final"] is True
assert continuity["current_zero_snapshot"]["terminal"] is True
assert continuity["current_zero_snapshot"]["permanent"] is True
assert continuity["current_zero_snapshot"]["mutable"] is False
assert continuity["future_admission_request_law"]["future_valid_admission_requests_allowed_under_law"] is True
assert continuity["future_admission_request_law"]["future_valid_admission_requests_must_target_future_snapshot"] is True
assert continuity["future_admission_request_law"]["future_valid_admission_requests_create_new_snapshot"] is True
assert continuity["future_admission_request_law"]["future_valid_admission_requests_do_not_mutate_current_zero_snapshot"] is True
assert continuity["future_admission_request_law"]["future_valid_admission_requests_do_not_mutate_terminal_snapshot"] is True

assert permanence["current_zero_admission_snapshot_permanent"] is True
assert permanence["current_zero_admission_snapshot_mutable"] is False
assert permanence["current_zero_admission_snapshot_terminal"] is True
assert permanence["future_valid_admission_requests_create_new_snapshot"] is True
assert permanence["future_valid_admission_requests_do_not_mutate_current_zero_snapshot"] is True
assert permanence["future_valid_admission_requests_do_not_mutate_terminal_snapshot"] is True

slots = slot_index["authority_object_slots"]
assert slot_index["authority_object_slot_count"] == 8
assert slots[0]["slot_id"] == "director_final_cut_authority"
assert slots[0]["required_authority_object"] == "DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"
assert slots[0]["slot_status"] == "UNFILLED"

for record in (obj, status):
    assert record["case_id"] == "CASE_001_THE_LAST_RENDER"
    assert record["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
    assert record["fork_scope"] == "FUTURE_VALID_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS_CREATE_NEW_SNAPSHOT_ONLY"
    assert record["future_continuity_seal_required"] is True
    assert record["future_continuity_seal_present"] is True
    assert record["permanence_seal_required"] is True
    assert record["permanence_seal_present"] is True
    assert record["current_zero_admission_snapshot_final"] is True
    assert record["current_zero_admission_snapshot_terminal"] is True
    assert record["current_zero_admission_snapshot_permanent"] is True
    assert record["current_zero_admission_snapshot_mutable"] is False
    assert record["current_zero_admission_snapshot_reopenable_by_future_request"] is False
    assert record["current_zero_admission_snapshot_reopenable_by_silence"] is False
    assert record["future_valid_admission_requests_allowed_under_law"] is True
    assert record["future_valid_admission_requests_require_explicit_request"] is True
    assert record["future_valid_admission_requests_require_validation"] is True
    assert record["future_valid_admission_requests_require_decision"] is True
    assert record["future_valid_admission_requests_require_enforcement_gate"] is True
    assert record["future_valid_admission_requests_must_target_future_snapshot"] is True
    assert record["future_valid_admission_requests_create_new_snapshot"] is True
    assert record["future_valid_admission_requests_fork_from_current_zero_snapshot"] is True
    assert record["future_valid_admission_requests_do_not_mutate_current_zero_snapshot"] is True
    assert record["future_valid_admission_requests_do_not_mutate_terminal_snapshot"] is True
    assert record["future_valid_admission_requests_do_not_reopen_current_zero_snapshot"] is True
    assert record["future_valid_admission_requests_do_not_convert_zero_snapshot_into_authority"] is True
    assert record["silent_slot_filling_forbidden"] is True
    assert record["silent_snapshot_mutation_forbidden"] is True
    assert record["implicit_snapshot_fork_forbidden"] is True
    assert record["authority_object_slot_count"] == 8
    assert record["accepted_authority_object_count_now"] == 0
    assert record["instantiated_authority_object_count_now"] == 0
    assert record["continuity_first_future_authority_slot_candidate_alias"] == "DIRECTOR_ACCEPTANCE_OBJECT"
    assert record["canonical_first_future_authority_slot_id"] == "director_final_cut_authority"
    assert record["canonical_first_future_authority_object"] == "DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"
    assert record["future_snapshot_fork_gate_passed"] is False
    assert record["future_snapshot_fork_gate_open_now"] is False
    assert record["future_snapshot_fork_gate_does_not_accept_authority_object_now"] is True
    assert record["future_snapshot_fork_gate_does_not_instantiate_authority_object_now"] is True
    assert record["future_snapshot_fork_gate_does_not_mutate_current_zero_snapshot"] is True
    assert record["future_snapshot_fork_gate_does_not_mutate_terminal_snapshot"] is True
    assert record["future_snapshot_fork_gate_does_not_satisfy_authority"] is True
    assert record["future_snapshot_fork_gate_does_not_advance_state"] is True
    assert record["future_snapshot_fork_gate_does_not_issue_motion_picture"] is True
    assert record["future_snapshot_fork_gate_does_not_admit_media"] is True
    assert record["future_snapshot_fork_gate_does_not_create_release_candidate"] is True
    assert record["authority_satisfied"] is False
    assert record["may_advance_now"] is False
    assert record["release_candidate_ready"] is False
    assert record["issued"] is False
    assert record["media_present"] is False

assert law["law_scope"] == "FUTURE_VALID_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS_CREATE_NEW_SNAPSHOT_ONLY"
for key in [
    "future_snapshot_fork_requires_future_continuity_seal",
    "future_snapshot_fork_requires_permanence_seal",
    "future_snapshot_fork_requires_slot_index",
    "current_zero_admission_snapshot_final",
    "current_zero_admission_snapshot_terminal",
    "current_zero_admission_snapshot_permanent",
    "current_zero_admission_snapshot_mutation_forbidden",
    "current_zero_admission_snapshot_reopening_by_future_request_forbidden",
    "terminal_snapshot_mutation_forbidden",
    "future_valid_admission_requests_allowed_under_law",
    "future_valid_admission_requests_require_explicit_request",
    "future_valid_admission_requests_require_validation",
    "future_valid_admission_requests_require_decision",
    "future_valid_admission_requests_require_enforcement_gate",
    "future_valid_admission_requests_must_target_future_snapshot",
    "future_valid_admission_requests_create_new_snapshot",
    "future_valid_admission_requests_fork_from_current_zero_snapshot",
    "future_valid_admission_requests_do_not_mutate_current_zero_snapshot",
    "future_valid_admission_requests_do_not_mutate_terminal_snapshot",
    "future_valid_admission_requests_do_not_reopen_current_zero_snapshot",
    "future_valid_admission_requests_do_not_convert_zero_snapshot_into_authority",
    "silent_slot_filling_forbidden",
    "silent_snapshot_mutation_forbidden",
    "implicit_snapshot_fork_forbidden"
]:
    assert law[key] is True, key

for key in [
    "future_snapshot_fork_gate_may_accept_authority_object_now",
    "future_snapshot_fork_gate_may_instantiate_authority_object_now",
    "future_snapshot_fork_gate_may_satisfy_authority",
    "future_snapshot_fork_gate_may_advance_state",
    "future_snapshot_fork_gate_may_issue_motion_picture",
    "future_snapshot_fork_gate_may_admit_media"
]:
    assert law[key] is False, key

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION FUTURE SNAPSHOT FORK GATE: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"FORK_SCOPE={obj['fork_scope']}")
print(f"FUTURE_CONTINUITY_SEAL_PRESENT={str(obj['future_continuity_seal_present']).lower()}")
print(f"PERMANENCE_SEAL_PRESENT={str(obj['permanence_seal_present']).lower()}")
print(f"CURRENT_ZERO_ADMISSION_SNAPSHOT_PERMANENT={str(obj['current_zero_admission_snapshot_permanent']).lower()}")
print(f"CURRENT_ZERO_ADMISSION_SNAPSHOT_MUTABLE={str(obj['current_zero_admission_snapshot_mutable']).lower()}")
print(f"CURRENT_ZERO_ADMISSION_SNAPSHOT_REOPENABLE_BY_FUTURE_REQUEST={str(obj['current_zero_admission_snapshot_reopenable_by_future_request']).lower()}")
print(f"FUTURE_VALID_ADMISSION_REQUESTS_CREATE_NEW_SNAPSHOT={str(obj['future_valid_admission_requests_create_new_snapshot']).lower()}")
print(f"FUTURE_VALID_ADMISSION_REQUESTS_FORK_FROM_CURRENT_ZERO_SNAPSHOT={str(obj['future_valid_admission_requests_fork_from_current_zero_snapshot']).lower()}")
print(f"FUTURE_VALID_ADMISSION_REQUESTS_DO_NOT_MUTATE_CURRENT_ZERO_SNAPSHOT={str(obj['future_valid_admission_requests_do_not_mutate_current_zero_snapshot']).lower()}")
print(f"FUTURE_VALID_ADMISSION_REQUESTS_DO_NOT_MUTATE_TERMINAL_SNAPSHOT={str(obj['future_valid_admission_requests_do_not_mutate_terminal_snapshot']).lower()}")
print(f"CANONICAL_FIRST_FUTURE_AUTHORITY_SLOT_ID={obj['canonical_first_future_authority_slot_id']}")
print(f"CANONICAL_FIRST_FUTURE_AUTHORITY_OBJECT={obj['canonical_first_future_authority_object']}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_PASSED={str(obj['future_snapshot_fork_gate_passed']).lower()}")
print(f"FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW={str(obj['future_snapshot_fork_gate_open_now']).lower()}")
print(f"AUTHORITY_SATISFIED={str(obj['authority_satisfied']).lower()}")
print(f"MAY_ADVANCE_NOW={str(obj['may_advance_now']).lower()}")
print(f"RELEASE_CANDIDATE_READY={str(obj['release_candidate_ready']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
PY
