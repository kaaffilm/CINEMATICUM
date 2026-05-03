#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_LAW.json
test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json
test -f AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.md
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_STATUS.json
test -d fixtures/authority_object_admission_requests/rejected
test -d authority_object_admission_requests

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_LAW.json")
corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_STATUS.json")
schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_LAW"
assert law["corpus_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json"
assert law["validator_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json"
assert law["schema_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json"
assert law["fixture_directory"] == "fixtures/authority_object_admission_requests/rejected"
assert law["live_request_directory"] == "authority_object_admission_requests"
assert law["law"]["fixtures_are_not_live_requests"] is True
assert law["law"]["each_fixture_must_be_rejected"] is True
assert law["law"]["rejected_fixtures_do_not_advance_state"] is True

assert corpus["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS"
assert corpus["case_id"] == "CASE_001_THE_LAST_RENDER"
assert corpus["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert corpus["validator_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json"
assert corpus["schema_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json"

assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_STATUS"
assert status["case_id"] == corpus["case_id"]
assert status["current_state"] == corpus["current_state"]

fixture_dir = Path(corpus["fixture_directory"])
live_dir = Path(corpus["live_request_directory"])

assert fixture_dir.exists()
assert live_dir.exists()
assert fixture_dir != live_dir
assert not str(fixture_dir).startswith(str(live_dir) + "/")

fixture_files = sorted(fixture_dir.glob("*.json"))
assert len(fixture_files) == corpus["rejection_fixture_count"] == status["rejection_fixture_count"]

live_files = sorted(live_dir.glob(schema["request_file_pattern"]))
assert live_files == [], [str(p) for p in live_files]

fixed = schema["required_fixed_values"]
assert fixed["media_payload_present"] is False
assert fixed["model_weight_payload_present"] is False
assert fixed["private_access_required"] is False
assert fixed["authority_satisfied_by_request"] is False
assert fixed["may_advance_state_by_request"] is False

def rejection_reason(obj):
    if "case_id" not in obj:
        return "missing_case_id"
    if obj.get("current_state") != "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED":
        return "wrong_current_state"
    if obj.get("authority_satisfied_by_request") is not False:
        return "authority_satisfied_by_request_true"
    if obj.get("media_payload_present") is not False:
        return "media_payload_present_true"
    if obj.get("private_access_required") is not False:
        return "private_access_required_true"
    if obj.get("model_weight_payload_present") is not False:
        return "model_weight_payload_present_true"
    if obj.get("may_advance_state_by_request") is not False:
        return "may_advance_state_by_request_true"
    return None

seen = []
for path in fixture_files:
    obj = json.loads(path.read_text(encoding="utf-8"))
    assert obj["fixture_type"] == "REJECTED_AUTHORITY_OBJECT_ADMISSION_REQUEST_FIXTURE", path
    expected = obj["expected_rejection_reason"]
    actual = rejection_reason(obj)
    assert actual == expected, f"{path}: expected {expected}, got {actual}"
    seen.append(actual)

assert sorted(seen) == sorted(corpus["expected_rejection_reasons"])

for obj in [corpus, status, validator, docket]:
    for key in [
        "admission_requests_present",
        "accepted_admission_requests_present",
        "instantiated_authority_objects_present",
        "authority_satisfied",
        "may_advance_now",
        "issued",
        "media_present"
    ]:
        assert obj[key] is False, f"{obj.get('object_type')}:{key}"

for obj in [corpus, status, validator, docket]:
    for key in ["admission_request_count"]:
        assert obj[key] == 0, f"{obj.get('object_type')}:{key}"

assert corpus["fixtures_are_live_requests"] is False
assert corpus["rejected_fixtures_are_admission_requests"] is False
assert status["fixtures_are_live_requests"] is False
assert status["rejected_fixtures_are_admission_requests"] is False

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == corpus["current_state"]
assert case["current_state"] == corpus["current_state"]
assert registry["current_active_state"] == corpus["current_state"]

text = Path("AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.md").read_text(encoding="utf-8")
for needle in [
    "fixtures are not live admission requests",
    "rejection_fixture_count=5",
    "admission_request_count=0",
    "authority_satisfied=false",
    "may_advance_now=false",
    "issued=false",
    "media_present=false"
]:
    assert needle in text, needle

print("CINEMATICUM AUTHORITY OBJECT ADMISSION REQUEST REJECTION CORPUS: PASS")
print("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("REJECTION_FIXTURE_COUNT=5")
print("FIXTURES_ARE_LIVE_REQUESTS=false")
print("ADMISSION_REQUEST_COUNT=0")
print("ALL_FIXTURES_REJECTED=true")
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
