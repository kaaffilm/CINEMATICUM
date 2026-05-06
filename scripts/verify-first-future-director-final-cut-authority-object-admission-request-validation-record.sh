#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

paths = {
    "request": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS/REQ_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json"),
    "validation": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_VALIDATION_RECORDS/VAL_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json"),
    "status": Path("CASES/CASE_001_THE_LAST_RENDER/FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATION_RECORD_STATUS.json"),
    "law": Path("CINEMATICUM_FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATION_RECORD_LAW.json"),
}

missing = [str(path) for path in paths.values() if not path.exists()]
if missing:
    raise SystemExit("missing required files:\n" + "\n".join(missing))

data = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}
request = data["request"]
validation = data["validation"]
status = data["status"]
law = data["law"]

def pick(mapping, *keys, default=None):
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default

def require(condition, message):
    if not condition:
        raise SystemExit(message)

request_id = "REQ_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"
record_id = "VAL_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"
slot_id = "director_final_cut_authority"
authority_object = "DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"
current_state = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"

require(pick(validation, "record_id") == record_id, "validation record_id mismatch")
require(pick(validation, "request_id") == request_id, "validation request_id mismatch")
require(pick(validation, "authority_slot_id", "slot_id") == slot_id, "validation slot mismatch")
require(pick(validation, "authority_object") == authority_object, "validation authority object mismatch")
require(pick(validation, "current_state") == current_state, "validation current_state mismatch")

require(pick(status, "record_id") == record_id, "status record_id mismatch")
require(pick(status, "request_id") == request_id, "status request_id mismatch")
require(pick(status, "current_state") == current_state, "status current_state mismatch")

require(pick(law, "record_id") == record_id, "law record_id mismatch")
require(pick(law, "request_id") == request_id, "law request_id mismatch")
require(pick(law, "canonical_authority_slot_id") == slot_id, "law slot mismatch")
require(pick(law, "canonical_authority_object") == authority_object, "law authority object mismatch")

request_text = json.dumps(request, sort_keys=True)
require(request_id in request_text, "request file does not contain canonical request id")
require(slot_id in request_text, "request file does not contain canonical slot id")
require(authority_object in request_text, "request file does not contain canonical authority object")

true_checks = {
    "REQUEST_TARGETS_FUTURE_SNAPSHOT": pick(validation, "request_targets_future_snapshot") is True,
    "REQUEST_SCHEMA_VALID": pick(validation, "request_schema_valid") is True,
    "SLOT_IDENTITY_VALID": pick(validation, "slot_identity_valid") is True,
    "AUTHORITY_OBJECT_IDENTITY_VALID": pick(validation, "authority_object_identity_valid") is True,
    "VALIDATION_IS_NOT_ACCEPTANCE": pick(law, "validation_is_not_acceptance") is True,
    "VALIDATION_IS_NOT_INSTANTIATION": pick(law, "validation_is_not_instantiation") is True,
    "VALIDATION_DOES_NOT_MUTATE_CURRENT_ZERO_SNAPSHOT": pick(law, "validation_does_not_mutate_current_zero_snapshot") is True,
    "VALIDATION_DOES_NOT_MUTATE_TERMINAL_SNAPSHOT": pick(law, "validation_does_not_mutate_terminal_snapshot") is True,
}

false_checks = {
    "VALIDATION_RECORD_ACCEPTS_REQUEST": pick(validation, "validation_record_accepts_request") is False,
    "VALIDATION_RECORD_REJECTS_REQUEST": pick(validation, "validation_record_rejects_request") is False,
    "VALIDATION_RECORD_INSTANTIATES_AUTHORITY_OBJECT": pick(validation, "validation_record_instantiates_authority_object") is False,
    "VALIDATION_RECORD_SATISFIES_AUTHORITY": pick(validation, "validation_record_satisfies_authority") is False,
    "VALIDATION_RECORD_ADVANCES_STATE": pick(validation, "validation_record_advances_state") is False,
    "VALIDATION_RECORD_CREATES_RELEASE_CANDIDATE": pick(validation, "validation_record_creates_release_candidate") is False,
    "VALIDATION_RECORD_ISSUES_MOTION_PICTURE": pick(validation, "validation_record_issues_motion_picture") is False,
    "VALIDATION_RECORD_ADMITS_MEDIA": pick(validation, "validation_record_admits_media") is False,
    "FUTURE_SNAPSHOT_FORK_GATE_PASSED": pick(validation, "future_snapshot_fork_gate_passed") is False,
    "FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW": pick(validation, "future_snapshot_fork_gate_open_now") is False,
    "AUTHORITY_SATISFIED": pick(status, "authority_satisfied") is False,
    "MAY_ADVANCE_NOW": pick(status, "may_advance_now") is False,
    "RELEASE_CANDIDATE_READY": pick(status, "release_candidate_ready") is False,
    "ISSUED": pick(status, "issued") is False,
    "MEDIA_PRESENT": pick(status, "media_present") is False,
}

failed = [name for name, ok in {**true_checks, **false_checks}.items() if not ok]
if failed:
    raise SystemExit("failed checks:\n" + "\n".join(failed))

print("CINEMATICUM FIRST FUTURE DIRECTOR FINAL CUT AUTHORITY OBJECT ADMISSION REQUEST VALIDATION RECORD: PASS")
print(f"CURRENT_STATE={current_state}")
print("VALIDATION_SCOPE=FUTURE_VALID_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS_ONLY")
print(f"REQUEST_ID={request_id}")
print(f"VALIDATION_RECORD_ID={record_id}")
print(f"AUTHORITY_SLOT_ID={slot_id}")
print(f"AUTHORITY_OBJECT={authority_object}")
print("REQUEST_TARGETS_FUTURE_SNAPSHOT=true")
print("REQUEST_SCHEMA_VALID=true")
print("SLOT_IDENTITY_VALID=true")
print("AUTHORITY_OBJECT_IDENTITY_VALID=true")
print("VALIDATION_RECORD_ACCEPTS_REQUEST=false")
print("VALIDATION_RECORD_INSTANTIATES_AUTHORITY_OBJECT=false")
print("ACCEPTED_DECISION_COUNT=0")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=0")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=0")
print("FUTURE_SNAPSHOT_FORK_GATE_PASSED=false")
print("FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW=false")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
