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
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json",
    "CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_STATUS.json",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.md",
]
for required_path in required_paths:
    assert Path(required_path).exists(), f"missing required object: {required_path}"

open_intake = load("CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE.json")
docket = load("CINEMATICUM_REAL_CASE_AUTHORITY_INTAKE_DOCKET.json")
slot_index = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX.json")
law = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW.json")
schema = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_STATUS.json")

assert open_intake["real_case_authority_intake_open"] is True
assert open_intake["authority_object_admission_requests_allowed"] is True
assert docket["object"] == "REAL_CASE_AUTHORITY_INTAKE_DOCKET"
assert docket["required_authority_object_count"] == 8
assert docket["live_authority_request_count"] == 0
assert docket["accepted_authority_object_count"] == 0

assert slot_index["object_type"] == "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX"
assert slot_index["real_case_authority_intake_open"] is True
assert slot_index["authority_object_slot_count"] == 8
assert slot_index["unfilled_authority_object_slot_count"] == 8
assert slot_index["accepted_authority_object_count"] == 0
assert slot_index["instantiated_authority_object_count"] == 0

assert law["object_type"] == "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW"
assert schema["object_type"] == "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA"
assert status["object_type"] == "CINEMATICUM_CASE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_STATUS"

for obj in (law, schema, status):
    assert obj["institution"] == "CINEMATICUM"
    assert obj["case_id"] == "CASE_001_THE_LAST_RENDER"
    assert obj["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
    assert obj["schema_only"] is True
    assert obj["real_case_authority_intake_open"] is True
    assert obj["authority_object_slot_count"] == 8
    assert obj["live_admission_request_count"] == 0
    assert obj["valid_admission_request_count"] == 0
    assert obj["accepted_authority_object_count"] == 0
    assert obj["instantiated_authority_object_count"] == 0
    assert obj["schema_does_not_create_live_requests"] is True
    assert obj["schema_does_not_validate_requests"] is True
    assert obj["schema_does_not_accept_requests"] is True
    assert obj["schema_does_not_instantiate_authority_objects"] is True
    assert obj["schema_does_not_satisfy_authority"] is True
    assert obj["schema_does_not_advance_state"] is True
    assert obj["schema_does_not_issue_motion_picture"] is True
    assert obj["schema_does_not_admit_media"] is True
    assert obj["schema_does_not_create_release_candidate"] is True
    assert obj["schema_does_not_reopen_current_snapshot"] is True
    assert obj["schema_does_not_create_new_snapshot"] is True
    assert obj["authority_satisfied"] is False
    assert obj["may_advance_now"] is False
    assert obj["release_candidate_ready"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False

slot_ids = [slot["slot_id"] for slot in slot_index["authority_object_slots"]]
assert schema["permitted_slot_ids"] == slot_ids

required_fields = schema["request_schema"]["required_fields"]
for field in [
    "request_id",
    "case_id",
    "target_slot_id",
    "proposed_authority_object_type",
    "accountable_actor",
    "authority_claim",
    "evidence_reference",
    "request_timestamp_utc",
    "statement_of_authority",
    "current_state_acknowledgement",
    "slot_index_acknowledgement",
    "non_media_payload_assertion",
]:
    assert field in required_fields

for forbidden in [
    "raw_media_payload",
    "model_weights",
    "private_key",
    "secret_token",
    "release_candidate_ready",
    "issued",
    "media_present",
    "authority_satisfied",
    "may_advance_now",
]:
    assert forbidden in schema["request_schema"]["forbidden_fields"]

request_dir = Path(schema["live_admission_request_directory"])
assert not request_dir.exists() or not any(request_dir.iterdir()), "live request directory must be absent or empty"

assert schema["object_is_non_star_seal"] is False
assert schema["object_is_negative_capability_seal"] is False

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REQUEST SCHEMA: PASS")
print("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("SCHEMA_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_PRESENT=true")
print("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_SEALED=true")
print("REAL_CASE_AUTHORITY_INTAKE_OPEN=true")
print("AUTHORITY_OBJECT_SLOT_COUNT=8")
print("LIVE_ADMISSION_REQUEST_COUNT=0")
print("VALID_ADMISSION_REQUEST_COUNT=0")
print("ACCEPTED_ADMISSION_REQUEST_COUNT=0")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("SCHEMA_ONLY=true")
print("SCHEMA_DOES_NOT_CREATE_LIVE_REQUESTS=true")
print("SCHEMA_DOES_NOT_VALIDATE_REQUESTS=true")
print("SCHEMA_DOES_NOT_ACCEPT_REQUESTS=true")
print("SCHEMA_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true")
print("SCHEMA_DOES_NOT_SATISFY_AUTHORITY=true")
print("SCHEMA_DOES_NOT_ADVANCE_STATE=true")
print("SCHEMA_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("SCHEMA_DOES_NOT_ADMIT_MEDIA=true")
print("SCHEMA_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("SCHEMA_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true")
print("SCHEMA_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
