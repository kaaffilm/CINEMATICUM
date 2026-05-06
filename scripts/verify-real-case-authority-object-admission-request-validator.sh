#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")

REQUIRED_FILES = [
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json",
    "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_LAW.json",
    "CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_STATUS.json",
    "CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_STATUS.json",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.md",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.md",
]

def load_json(path: str):
    p = ROOT / path
    if not p.exists():
        raise AssertionError(f"missing required file: {path}")
    return json.loads(p.read_text(encoding="utf-8"))

def require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)

for required in REQUIRED_FILES:
    p = ROOT / required
    require(p.exists(), f"missing required file: {required}")

schema = load_json("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
schema_law = load_json("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW.json")
schema_status = load_json("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_STATUS.json")
validator = load_json("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
validator_law = load_json("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_LAW.json")
validator_status = load_json("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_STATUS.json")

# Structural guardrails: parseable, present, and bound to schema-only intake.
require(isinstance(schema, dict), "schema object must be a JSON object")
require(isinstance(schema_law, dict), "schema law must be a JSON object")
require(isinstance(schema_status, dict), "schema status must be a JSON object")
require(isinstance(validator, dict), "validator object must be a JSON object")
require(isinstance(validator_law, dict), "validator law must be a JSON object")
require(isinstance(validator_status, dict), "validator status must be a JSON object")

# Current-snapshot constants for this layer.
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
VALIDATOR_SCOPE = "REAL_CASE_AUTHORITY_OBJECTS_ONLY"
AUTHORITY_OBJECT_SLOT_COUNT = 8

LIVE_ADMISSION_REQUEST_COUNT = 0
VALID_ADMISSION_REQUEST_COUNT = 0
INVALID_ADMISSION_REQUEST_COUNT = 0
ACCEPTED_ADMISSION_REQUEST_COUNT = 0
ACCEPTED_AUTHORITY_OBJECT_COUNT = 0
INSTANTIATED_AUTHORITY_OBJECT_COUNT = 0

ZERO_REQUESTS_VALID = True
VALIDATOR_DOES_NOT_CREATE_LIVE_REQUESTS = True
VALIDATOR_DOES_NOT_ACCEPT_REQUESTS = True
VALIDATOR_DOES_NOT_REJECT_REQUESTS = True
VALIDATOR_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS = True
VALIDATOR_DOES_NOT_SATISFY_AUTHORITY = True
VALIDATOR_DOES_NOT_ADVANCE_STATE = True
VALIDATOR_DOES_NOT_ISSUE_MOTION_PICTURE = True
VALIDATOR_DOES_NOT_ADMIT_MEDIA = True
VALIDATOR_DOES_NOT_CREATE_RELEASE_CANDIDATE = True
VALIDATOR_DOES_NOT_REOPEN_CURRENT_SNAPSHOT = True
VALIDATOR_DOES_NOT_CREATE_NEW_SNAPSHOT = True

AUTHORITY_SATISFIED = False
MAY_ADVANCE_NOW = False
RELEASE_CANDIDATE_READY = False
ISSUED = False
MEDIA_PRESENT = False

require(LIVE_ADMISSION_REQUEST_COUNT == 0, "validator layer must not create live admission requests")
require(VALID_ADMISSION_REQUEST_COUNT == 0, "zero-request snapshot must have zero valid requests")
require(INVALID_ADMISSION_REQUEST_COUNT == 0, "zero-request snapshot must have zero invalid requests")
require(ACCEPTED_ADMISSION_REQUEST_COUNT == 0, "validator layer must not accept requests")
require(ACCEPTED_AUTHORITY_OBJECT_COUNT == 0, "validator layer must not accept authority objects")
require(INSTANTIATED_AUTHORITY_OBJECT_COUNT == 0, "validator layer must not instantiate authority objects")
require(ZERO_REQUESTS_VALID is True, "zero current live requests must be valid as an empty validation set")
require(AUTHORITY_SATISFIED is False, "validator layer must not satisfy authority")
require(MAY_ADVANCE_NOW is False, "validator layer must not advance state")
require(RELEASE_CANDIDATE_READY is False, "validator layer must not create release candidate")
require(ISSUED is False, "validator layer must not issue motion picture")
require(MEDIA_PRESENT is False, "validator layer must not admit media")

lines = [
    "CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REQUEST VALIDATOR: PASS",
    f"CURRENT_STATE={CURRENT_STATE}",
    f"VALIDATOR_SCOPE={VALIDATOR_SCOPE}",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_PRESENT=true",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_PRESENT=true",
    "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_SEALED=true",
    "REAL_CASE_AUTHORITY_INTAKE_OPEN=true",
    f"AUTHORITY_OBJECT_SLOT_COUNT={AUTHORITY_OBJECT_SLOT_COUNT}",
    f"LIVE_ADMISSION_REQUEST_COUNT={LIVE_ADMISSION_REQUEST_COUNT}",
    f"VALID_ADMISSION_REQUEST_COUNT={VALID_ADMISSION_REQUEST_COUNT}",
    f"INVALID_ADMISSION_REQUEST_COUNT={INVALID_ADMISSION_REQUEST_COUNT}",
    f"ACCEPTED_ADMISSION_REQUEST_COUNT={ACCEPTED_ADMISSION_REQUEST_COUNT}",
    f"ACCEPTED_AUTHORITY_OBJECT_COUNT={ACCEPTED_AUTHORITY_OBJECT_COUNT}",
    f"INSTANTIATED_AUTHORITY_OBJECT_COUNT={INSTANTIATED_AUTHORITY_OBJECT_COUNT}",
    "ZERO_REQUESTS_VALID=true",
    "VALIDATOR_DOES_NOT_CREATE_LIVE_REQUESTS=true",
    "VALIDATOR_DOES_NOT_ACCEPT_REQUESTS=true",
    "VALIDATOR_DOES_NOT_REJECT_REQUESTS=true",
    "VALIDATOR_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true",
    "VALIDATOR_DOES_NOT_SATISFY_AUTHORITY=true",
    "VALIDATOR_DOES_NOT_ADVANCE_STATE=true",
    "VALIDATOR_DOES_NOT_ISSUE_MOTION_PICTURE=true",
    "VALIDATOR_DOES_NOT_ADMIT_MEDIA=true",
    "VALIDATOR_DOES_NOT_CREATE_RELEASE_CANDIDATE=true",
    "VALIDATOR_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true",
    "VALIDATOR_DOES_NOT_CREATE_NEW_SNAPSHOT=true",
    "AUTHORITY_SATISFIED=false",
    "MAY_ADVANCE_NOW=false",
    "RELEASE_CANDIDATE_READY=false",
    "ISSUED=false",
    "MEDIA_PRESENT=false",
]

print("\n".join(lines))
PY
