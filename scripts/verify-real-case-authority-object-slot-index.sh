#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

def load(path: str) -> dict:
    p = Path(path)
    assert p.exists(), f"missing {path}"
    return json.loads(p.read_text(encoding="utf-8"))

required_paths = [
    "CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_INTAKE_DOCKET.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX_LAW.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX.json",
    "CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX_STATUS.json",
    "REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX.md",
]
for required_path in required_paths:
    assert Path(required_path).exists(), f"missing required object: {required_path}"

open_intake = load("CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE.json")
docket = load("CINEMATICUM_REAL_CASE_AUTHORITY_INTAKE_DOCKET.json")
law = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX_LAW.json")
index = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX_STATUS.json")

assert open_intake.get("object_type") == "CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE"
assert open_intake.get("intake_object") == "OPEN_REAL_CASE_AUTHORITY_INTAKE"
assert open_intake.get("real_case_authority_intake_open") is True
assert open_intake.get("authority_object_admission_requests_allowed") is True

assert docket.get("object") == "REAL_CASE_AUTHORITY_INTAKE_DOCKET"
assert docket.get("docket_scope") == "REAL_CASE_AUTHORITY_OBJECTS_ONLY"
assert docket.get("depends_on") == "OPEN_REAL_CASE_AUTHORITY_INTAKE"
assert docket.get("required_authority_object_count") == 8
assert docket.get("live_authority_request_count") == 0
assert docket.get("accepted_authority_object_count") == 0
assert docket.get("real_case_authority_intake_open") is True

assert law["object_type"] == "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX_LAW"
assert index["object_type"] == "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX"
assert status["object_type"] == "CINEMATICUM_CASE_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX_STATUS"

for obj in (law, index, status):
    assert obj["institution"] == "CINEMATICUM"
    assert obj["case_id"] == "CASE_001_THE_LAST_RENDER"
    assert obj["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["release_candidate_ready"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False

slots = index["authority_object_slots"]
assert len(slots) == 8
assert index["authority_object_slot_count"] == 8
assert index["unfilled_authority_object_slot_count"] == 8
assert index["accepted_authority_object_count"] == 0
assert index["instantiated_authority_object_count"] == 0
assert status["authority_object_slot_count"] == 8
assert status["unfilled_authority_object_slot_count"] == 8
assert status["accepted_authority_object_count"] == 0
assert status["instantiated_authority_object_count"] == 0

assert [slot["slot_number"] for slot in slots] == list(range(1, 9))
slot_ids = [slot["slot_id"] for slot in slots]
assert len(set(slot_ids)) == 8

required_slot_ids = {
    "director_final_cut_authority",
    "editorial_timeline_authority",
    "sound_final_mix_authority",
    "color_grade_authority",
    "release_delivery_authority",
    "archival_proof_chain_authority",
    "outsider_replay_authority",
    "terminal_closure_authority",
}
assert set(slot_ids) == required_slot_ids

for slot in slots:
    assert slot["slot_status"] == "UNFILLED"
    assert slot["admission_request_present"] is False
    assert slot["accepted_decision_present"] is False
    assert slot["instantiated_authority_object_present"] is False
    assert slot["required_authority_object"].endswith("_AUTHORITY_OBJECT")

for key in [
    "slot_index_does_not_satisfy_authority",
    "slot_index_does_not_advance_state",
    "slot_index_does_not_issue_motion_picture",
    "slot_index_does_not_admit_media",
    "slot_index_does_not_create_release_candidate",
    "slot_index_does_not_reopen_current_snapshot",
    "slot_index_does_not_create_new_snapshot",
]:
    assert law[key] is True
    assert index[key] is True
    assert status[key] is True

assert index["real_case_authority_intake_open"] is True
assert index["authority_object_admission_requests_allowed"] is True
assert index["object_is_non_star_seal"] is False
assert index["object_is_negative_capability_seal"] is False

print("CINEMATICUM REAL CASE AUTHORITY OBJECT SLOT INDEX: PASS")
print("CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
print("SLOT_INDEX_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX_SEALED=true")
print("REAL_CASE_AUTHORITY_INTAKE_OPEN=true")
print("AUTHORITY_OBJECT_SLOT_COUNT=8")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=8")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("OBJECT_IS_NON_STAR_SEAL=false")
print("OBJECT_IS_NEGATIVE_CAPABILITY_SEAL=false")
print("SLOT_INDEX_DOES_NOT_SATISFY_AUTHORITY=true")
print("SLOT_INDEX_DOES_NOT_ADVANCE_STATE=true")
print("SLOT_INDEX_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("SLOT_INDEX_DOES_NOT_ADMIT_MEDIA=true")
print("SLOT_INDEX_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("SLOT_INDEX_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true")
print("SLOT_INDEX_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
