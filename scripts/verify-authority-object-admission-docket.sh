#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET_LAW.json
test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json
test -f AUTHORITY_OBJECT_ADMISSION_DOCKET.md
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_DOCKET_STATUS.json
test -d authority_object_admission_requests
test -f authority_object_admission_requests/README.md
test -d authority_objects

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET_LAW.json")
docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_DOCKET_STATUS.json")
inst_gate = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
template_kit = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

current = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET_LAW"
assert law["law"]["silent_authority_object_instantiation_forbidden"] is True
assert law["law"]["request_required_before_authority_object"] is True
assert law["law"]["request_must_be_public"] is True
assert law["law"]["request_must_be_case_bound"] is True
assert law["law"]["request_must_reference_template"] is True
assert law["law"]["request_must_reference_target_authority_object"] is True
assert law["law"]["request_must_include_actor"] is True
assert law["law"]["request_must_include_utc_timestamp"] is True
assert law["law"]["request_must_include_evidence_references"] is True
assert law["law"]["request_must_include_requested_state_effect"] is True
assert law["law"]["request_must_pass_docket_verification"] is True
assert law["law"]["docket_does_not_itself_admit_request"] is True
assert law["law"]["docket_does_not_itself_instantiate_authority"] is True
assert law["law"]["docket_does_not_itself_advance_state"] is True
assert law["law"]["docket_does_not_issue_film"] is True

assert docket["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET"
assert docket["current_state"] == current
assert docket["request_directory"] == "authority_object_admission_requests"
assert docket["instantiated_authority_directory"] == "authority_objects"
assert docket["template_directory"] == "templates/authority_objects"

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
    "media_present",
    "outsider_replay_passed",
    "terminal_closure_present"
]:
    assert docket[key] is False, key
    assert status[key] is False, key

for key in [
    "admission_request_count",
    "accepted_admission_request_count",
    "rejected_admission_request_count",
    "pending_admission_request_count"
]:
    assert docket[key] == 0, key
    assert status[key] == 0, key

assert docket["required_authority_objects_missing"] is True
assert status["required_authority_objects_missing"] is True
assert docket["currently_allowed_requests"] == []
assert set(docket["allowed_request_statuses"]) == {"PENDING", "REJECTED", "ACCEPTED"}

minimum = {
    "object_type",
    "schema_version",
    "case_id",
    "target_authority_object",
    "source_template",
    "requesting_actor",
    "request_timestamp_utc",
    "authority_basis",
    "evidence_references",
    "requested_state_effect",
    "requested_admission_status"
}
assert minimum.issubset(set(docket["request_schema_minimum_fields"]))

assert inst_gate["instantiated_authority_objects_present"] is False
assert inst_gate["authority_satisfied"] is False
assert inst_gate["may_advance_now"] is False
assert template_kit["template_only"] is True
assert template_kit["authority_satisfied"] is False

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == current
assert case["current_state"] == current

request_json = sorted(Path("authority_object_admission_requests").glob("*.json"))
authority_json = sorted(Path("authority_objects").glob("*.json"))
assert request_json == [], [str(p) for p in request_json]
assert authority_json == [], [str(p) for p in authority_json]

for future in docket["currently_forbidden_silent_targets"]:
    assert not Path(future).exists(), future
    assert not Path("authority_objects", future).exists(), f"authority_objects/{future}"

text = Path("AUTHORITY_OBJECT_ADMISSION_DOCKET.md").read_text(encoding="utf-8")
for needle in [
    "The admission docket is not an authority object",
    "admission_requests_present=false",
    "admission_request_count=0",
    "accepted_admission_requests_present=false",
    "instantiated_authority_objects_present=false",
    "authority_satisfied=false",
    "may_advance_now=false",
    "issued=false",
    "media_present=false"
]:
    assert needle in text, needle

print("CINEMATICUM AUTHORITY OBJECT ADMISSION DOCKET: PASS")
print("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("ADMISSION_REQUESTS_PRESENT=false")
print("ADMISSION_REQUEST_COUNT=0")
print("ACCEPTED_ADMISSION_REQUESTS_PRESENT=false")
print("INSTANTIATED_AUTHORITY_OBJECTS_PRESENT=false")
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
