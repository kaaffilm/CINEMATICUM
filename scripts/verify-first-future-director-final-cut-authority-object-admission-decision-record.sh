#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")

status_path = ROOT / "CASES/CASE_001_THE_LAST_RENDER/FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_ADMISSION_DECISION_RECORD_STATUS.json"
law_path = ROOT / "CINEMATICUM_FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_ADMISSION_DECISION_RECORD_LAW.json"
decision_path = ROOT / "CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_RECORDS/DEC_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json"
validation_path = ROOT / "CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_VALIDATION_RECORDS/VAL_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json"
validation_status_path = ROOT / "CASES/CASE_001_THE_LAST_RENDER/FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATION_RECORD_STATUS.json"
request_status_path = ROOT / "CASES/CASE_001_THE_LAST_RENDER/FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_ADMISSION_REQUEST_STATUS.json"

def load(path, optional=False):
    if not path.exists():
        if optional:
            return {}
        raise SystemExit(f"missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def first(obj, *keys):
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None

def bool_str(value):
    return str(value).lower() if isinstance(value, bool) else value

status = load(status_path)
law = load(law_path)
decision = load(decision_path)
validation = load(validation_path)
validation_status = load(validation_status_path)
request_status = load(request_status_path, optional=True)

expected = {
    "current_state": "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS",
    "decision_scope": "FUTURE_VALID_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS_ONLY",
    "request_id": "REQ_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT",
    "validation_record_id": "VAL_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT",
    "decision_record_id": "DEC_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT",
    "authority_slot_id": "director_final_cut_authority",
    "authority_object": "DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT",
}

for key, value in expected.items():
    if status.get(key) != value:
        raise SystemExit(f"status {key} mismatch: {status.get(key)!r}")

for key in [
    "current_state",
    "decision_scope",
    "request_id",
    "validation_record_id",
    "decision_record_id",
    "authority_slot_id",
    "authority_object",
]:
    if law.get(key) != expected[key]:
        raise SystemExit(f"law {key} mismatch: {law.get(key)!r}")

for key in [
    "request_id",
    "validation_record_id",
    "decision_record_id",
    "authority_slot_id",
    "authority_object",
]:
    if decision.get(key) != expected[key]:
        raise SystemExit(f"decision {key} mismatch: {decision.get(key)!r}")

validation_id = first(
    validation,
    "validation_record_id",
    "record_id",
    "id",
    "validation_id",
    "authority_object_admission_validation_record_id",
)
if validation_id is None:
    validation_id = first(
        validation_status,
        "validation_record_id",
        "record_id",
        "id",
        "validation_id",
        "authority_object_admission_validation_record_id",
    )

if validation_id != expected["validation_record_id"]:
    raise SystemExit(f"validation record id mismatch: {validation_id!r}")

validation_request_id = first(
    validation,
    "request_id",
    "admission_request_id",
    "authority_object_admission_request_id",
    "real_case_authority_object_admission_request_id",
)
if validation_request_id is None:
    validation_request_id = first(
        validation_status,
        "request_id",
        "admission_request_id",
        "authority_object_admission_request_id",
        "real_case_authority_object_admission_request_id",
    )

if validation_request_id != expected["request_id"]:
    raise SystemExit(f"validation request id mismatch: {validation_request_id!r}")

# Prior request-status is corroborative only. Field naming drift there must not
# invalidate a decision record whose canonical dependency is VAL_001.
request_status_id = first(
    request_status,
    "request_id",
    "admission_request_id",
    "authority_object_admission_request_id",
    "real_case_authority_object_admission_request_id",
    "id",
)
if request_status_id is not None and request_status_id != expected["request_id"]:
    raise SystemExit(f"request status id mismatch: {request_status_id!r}")

request_targets_future = first(
    request_status,
    "request_targets_future_snapshot",
    "targets_future_snapshot",
    "future_snapshot_targeted",
)
if request_targets_future is not None and request_targets_future is not True:
    raise SystemExit("request status does not target future snapshot")

validated_truths = {
    "request_targets_future_snapshot": first(validation, "request_targets_future_snapshot", "targets_future_snapshot"),
    "request_schema_valid": first(validation, "request_schema_valid", "schema_valid"),
    "slot_identity_valid": first(validation, "slot_identity_valid"),
    "authority_object_identity_valid": first(validation, "authority_object_identity_valid"),
}

for key, value in list(validated_truths.items()):
    if value is None:
        validated_truths[key] = first(validation_status, key)

for key, value in validated_truths.items():
    if value is not True:
        raise SystemExit(f"validated prior field {key} must be true")

true_status = [
    "request_targets_future_snapshot",
    "request_schema_valid",
    "slot_identity_valid",
    "authority_object_identity_valid",
    "decision_record_accepts_request",
]
for key in true_status:
    if status.get(key) is not True:
        raise SystemExit(f"{key} must be true")

false_status = [
    "validation_record_accepts_request",
    "decision_record_instantiates_authority_object",
    "future_snapshot_fork_gate_passed",
    "future_snapshot_fork_gate_open_now",
    "authority_satisfied",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present",
]
for key in false_status:
    if status.get(key) is not False:
        raise SystemExit(f"{key} must be false")

counts = {
    "accepted_decision_count": 1,
    "accepted_authority_object_count": 0,
    "instantiated_authority_object_count": 0,
}
for key, value in counts.items():
    if status.get(key) != value:
        raise SystemExit(f"{key} must be {value}")

decision_truths = {
    "accepted": True,
    "rejected": False,
    "request_targets_future_snapshot": True,
    "request_schema_valid": True,
    "slot_identity_valid": True,
    "authority_object_identity_valid": True,
    "instantiates_authority_object": False,
    "future_snapshot_fork_gate_passed": False,
    "future_snapshot_fork_gate_open_now": False,
    "authority_satisfied": False,
    "may_advance_now": False,
    "release_candidate_ready": False,
    "issued": False,
    "media_present": False,
}
for key, value in decision_truths.items():
    if decision.get(key) is not value:
        raise SystemExit(f"decision {key} must be {value!r}")

if law.get("decision_record_accepts_request") is not True:
    raise SystemExit("law must accept request")

for key in [
    "decision_record_instantiates_authority_object",
    "decision_record_satisfies_authority",
    "decision_record_advances_state",
    "decision_record_creates_release_candidate",
    "decision_record_issues_motion_picture",
    "decision_record_admits_media",
    "decision_record_opens_future_snapshot_fork_gate_now",
    "decision_record_mutates_current_zero_snapshot",
    "decision_record_mutates_terminal_snapshot",
]:
    if law.get(key) is not False:
        raise SystemExit(f"law {key} must be false")

print("CINEMATICUM FIRST FUTURE DIRECTOR FINAL CUT AUTHORITY OBJECT ADMISSION DECISION RECORD: PASS")
for key in [
    "current_state",
    "decision_scope",
    "request_id",
    "validation_record_id",
    "decision_record_id",
    "authority_slot_id",
    "authority_object",
    "request_targets_future_snapshot",
    "request_schema_valid",
    "slot_identity_valid",
    "authority_object_identity_valid",
    "decision_record_accepts_request",
    "decision_record_instantiates_authority_object",
    "accepted_decision_count",
    "accepted_authority_object_count",
    "instantiated_authority_object_count",
    "future_snapshot_fork_gate_passed",
    "future_snapshot_fork_gate_open_now",
    "authority_satisfied",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present",
]:
    print(f"{key.upper()}={bool_str(status[key])}")
PY
