#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW.json
test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json
test -f AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.md
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_STATUS.json
test -d authority_object_admission_requests

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW.json")
schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_STATUS.json")
docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
gate = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_LAW"
assert law["schema_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json"
assert law["docket_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json"
assert law["request_directory"] == "authority_object_admission_requests"
assert law["law"]["admission_requests_must_be_machine_readable"] is True
assert law["law"]["admission_requests_must_not_advance_state"] is True
assert law["law"]["admission_requests_must_not_issue_film"] is True

assert schema["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA"
assert schema["case_id"] == "CASE_001_THE_LAST_RENDER"
assert schema["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert schema["request_directory"] == "authority_object_admission_requests"
assert schema["request_file_pattern"] == "AUTHORITY_OBJECT_ADMISSION_REQUEST_*.json"
assert schema["schema_only"] is True

required = set(schema["required_fields"])
for key in [
    "object_type",
    "schema_version",
    "request_id",
    "case_id",
    "requested_authority_object_type",
    "requested_authority_template",
    "requester_assertion",
    "evidence_references",
    "media_payload_present",
    "model_weight_payload_present",
    "private_access_required",
    "requested_admission_status",
    "authority_satisfied_by_request",
    "may_advance_state_by_request"
]:
    assert key in required, key

fixed = schema["required_fixed_values"]
assert fixed["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST"
assert fixed["case_id"] == "CASE_001_THE_LAST_RENDER"
assert fixed["media_payload_present"] is False
assert fixed["model_weight_payload_present"] is False
assert fixed["private_access_required"] is False
assert fixed["requested_admission_status"] == "PENDING"
assert fixed["authority_satisfied_by_request"] is False
assert fixed["may_advance_state_by_request"] is False

allowed = set(schema["allowed_requested_authority_object_types"])
for authority_type in [
    "DIRECTOR_ACCEPTANCE_OBJECT",
    "FINAL_CUT_TIMELINE_LOCK",
    "MEDIA_HASH_MANIFEST",
    "SOUND_MIX_LOCK",
    "COLOR_GRADE_LOCK",
    "REPLAY_EXECUTION_REPORT",
    "ADMISSIBILITY_VERDICT",
    "TERMINAL_CLOSURE_CANDIDATE"
]:
    assert authority_type in allowed, authority_type

for obj in [schema, status, docket]:
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

    for key in [
        "admission_request_count",
        "accepted_admission_request_count",
        "rejected_admission_request_count",
        "pending_admission_request_count"
    ]:
        assert obj[key] == 0, f"{obj.get('object_type')}:{key}"

assert gate["instantiated_authority_objects_present"] is False
assert gate["authority_satisfied"] is False
assert gate["may_advance_now"] is False

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == schema["current_state"]
assert case["current_state"] == schema["current_state"]
assert registry["current_active_state"] == schema["current_state"]

request_dir = Path("authority_object_admission_requests")
request_files = sorted(request_dir.glob("AUTHORITY_OBJECT_ADMISSION_REQUEST_*.json"))
assert request_files == [], [str(p) for p in request_files]

text = Path("AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.md").read_text(encoding="utf-8")
for needle in [
    "does not admit any authority object",
    "does not instantiate any authority object",
    "does not satisfy authority",
    "does not advance state",
    "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED",
    "AUTHORITY_OBJECT_ADMISSION_REQUEST_*.json",
    "authority_satisfied_by_request=false",
    "may_advance_state_by_request=false"
]:
    assert needle in text, needle

print("CINEMATICUM AUTHORITY OBJECT ADMISSION REQUEST SCHEMA: PASS")
print("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("SCHEMA_ONLY=true")
print("ADMISSION_REQUESTS_PRESENT=false")
print("ADMISSION_REQUEST_COUNT=0")
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
