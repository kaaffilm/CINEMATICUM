#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_LAW.json
test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json
test -f AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.md
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_STATUS.json
test -d authority_object_admission_requests

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_LAW.json")
validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_STATUS.json")
schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
gate = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_LAW"
assert law["validator_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json"
assert law["schema_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json"
assert law["docket_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json"
assert law["request_directory"] == "authority_object_admission_requests"
assert law["law"]["validator_must_scan_request_directory"] is True
assert law["law"]["validator_must_accept_zero_requests"] is True
assert law["law"]["validator_must_not_admit_requests"] is True
assert law["law"]["validator_must_not_advance_state"] is True

assert validator["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR"
assert validator["case_id"] == "CASE_001_THE_LAST_RENDER"
assert validator["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert validator["schema_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json"
assert validator["request_directory"] == schema["request_directory"]
assert validator["request_file_pattern"] == schema["request_file_pattern"]
assert validator["zero_requests_valid"] is True

assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_STATUS"
assert status["case_id"] == validator["case_id"]
assert status["current_state"] == validator["current_state"]
assert status["validator_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json"
assert status["zero_requests_valid"] is True

request_dir = Path(schema["request_directory"])
request_files = sorted(request_dir.glob(schema["request_file_pattern"]))
assert request_files == [], [str(p) for p in request_files]

for obj in [validator, status, schema, docket]:
    for key in [
        "admission_requests_present",
        "accepted_admission_requests_present",
        "rejected_admission_requests_present",
        "pending_admission_requests_present",
        "instantiated_authority_objects_present",
        "authority_satisfied",
        "may_advance_now",
        "release_candidate_ready",
        "issued",
        "media_present"
    ]:
        assert obj[key] is False, f"{obj.get('object_type')}:{key}"

for obj in [validator, status]:
    for key in [
        "admission_request_count",
        "valid_admission_request_count",
        "invalid_admission_request_count",
        "accepted_admission_request_count",
        "rejected_admission_request_count",
        "pending_admission_request_count"
    ]:
        assert obj[key] == 0, f"{obj.get('object_type')}:{key}"

fixed = schema["required_fixed_values"]
assert fixed["media_payload_present"] is False
assert fixed["model_weight_payload_present"] is False
assert fixed["private_access_required"] is False
assert fixed["authority_satisfied_by_request"] is False
assert fixed["may_advance_state_by_request"] is False

assert gate["instantiated_authority_objects_present"] is False
assert gate["authority_satisfied"] is False
assert gate["may_advance_now"] is False

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == validator["current_state"]
assert case["current_state"] == validator["current_state"]
assert registry["current_active_state"] == validator["current_state"]

text = Path("AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.md").read_text(encoding="utf-8")
for needle in [
    "does not create requests",
    "does not accept requests",
    "does not reject requests",
    "does not admit authority objects",
    "does not instantiate authority objects",
    "does not advance state",
    "zero_requests_valid=true",
    "admission_request_count=0"
]:
    assert needle in text, needle

print("CINEMATICUM AUTHORITY OBJECT ADMISSION REQUEST VALIDATOR: PASS")
print("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("ZERO_REQUESTS_VALID=true")
print("ADMISSION_REQUESTS_PRESENT=false")
print("ADMISSION_REQUEST_COUNT=0")
print("VALID_ADMISSION_REQUEST_COUNT=0")
print("INVALID_ADMISSION_REQUEST_COUNT=0")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY

MEDIA_OR_MODEL="$(find . -type f \
  \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.avi' -o -iname '*.mkv' -o -iname '*.webm' \
     -o -iname '*.wav' -o -iname '*.aiff' -o -iname '*.flac' -o -iname '*.mp3' \
     -o -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.tiff' -o -iname '*.exr' -o -iname '*.dpx' \
     -o -iname '*.ckpt' -o -iname '*.safetensors' -o -iname '*.onnx' -o -iname '*.pt' -o -iname '*.pth' -o -iname '*.gguf' \) \
  -not -path './.git/*' | sort || true)"

if test -n "$MEDIA_OR_MODEL"; then
  printf "forbidden media/model artifact found:\n%s\n" "$MEDIA_OR_MODEL" >&2
  exit 1
fi
