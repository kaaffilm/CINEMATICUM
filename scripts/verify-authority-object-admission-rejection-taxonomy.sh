#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_LAW.json
test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json
test -f AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.md
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_STATUS.json
test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json
test -f CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_LAW.json")
taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_STATUS.json")
corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_LAW"
assert law["taxonomy_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json"
assert law["validator_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json"
assert law["corpus_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json"
assert law["schema_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json"

for key in [
    "all_rejection_reasons_must_be_canonical",
    "validator_may_not_emit_uncatalogued_rejection_reason",
    "rejection_corpus_must_cover_required_reason_codes",
    "taxonomy_does_not_create_live_requests",
    "taxonomy_does_not_accept_requests",
    "taxonomy_does_not_instantiate_authority_objects",
    "taxonomy_does_not_satisfy_authority",
    "taxonomy_does_not_advance_state"
]:
    assert law["law"][key] is True, key

assert taxonomy["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY"
assert taxonomy["case_id"] == "CASE_001_THE_LAST_RENDER"
assert taxonomy["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert taxonomy["validator_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json"
assert taxonomy["corpus_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json"
assert taxonomy["schema_owner"] == "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json"

assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_STATUS"
assert status["case_id"] == taxonomy["case_id"]
assert status["current_state"] == taxonomy["current_state"]

reasons = taxonomy["canonical_rejection_reasons"]
codes = [r["code"] for r in reasons]
assert len(codes) == taxonomy["canonical_rejection_reason_count"] == 9
assert len(codes) == len(set(codes)), "duplicate rejection code"

required_codes = {
    "missing_case_id",
    "wrong_case_id",
    "wrong_current_state",
    "unknown_authority_object_type",
    "authority_satisfied_by_request_true",
    "may_advance_state_by_request_true",
    "media_payload_present_true",
    "model_weight_payload_present_true",
    "private_access_required_true",
}
assert set(codes) == required_codes

covered = set(taxonomy["covered_rejection_reasons"])
uncovered = set(taxonomy["uncovered_rejection_reasons"])
assert covered | uncovered == required_codes
assert covered & uncovered == set()
assert len(covered) == status["covered_rejection_reason_count"] == 5
assert len(uncovered) == status["uncovered_rejection_reason_count"] == 4

assert set(corpus["expected_rejection_reasons"]) == covered
assert corpus["rejection_fixture_count"] == taxonomy["required_corpus_reason_count"] == status["required_corpus_reason_count"] == 5
assert corpus["rejected_fixture_count"] == 5
assert corpus["fixtures_are_live_requests"] is False
assert corpus["rejected_fixtures_are_admission_requests"] is False

fixture_dir = Path(corpus["fixture_directory"])
fixtures = sorted(fixture_dir.glob("*.json"))
fixture_reasons = {
    json.loads(path.read_text(encoding="utf-8"))["expected_rejection_reason"]
    for path in fixtures
}
assert fixture_reasons == covered
assert len(fixtures) == 5

for reason in reasons:
    assert reason["severity"] == "fatal"
    assert reason["class"] in {
        "identity",
        "state",
        "authority_object",
        "authority_boundary",
        "state_boundary",
        "payload_boundary",
        "public_replay_boundary"
    }
    assert isinstance(reason["meaning"], str) and reason["meaning"]
    assert reason["covered_by_rejection_corpus"] == (reason["code"] in covered)

assert taxonomy["taxonomy_complete_for_current_validator"] is True
assert taxonomy["corpus_complete_for_required_reasons"] is True
assert status["taxonomy_complete_for_current_validator"] is True
assert status["corpus_complete_for_required_reasons"] is True

live_dir = Path(schema["request_directory"])
live_files = sorted(live_dir.glob(schema["request_file_pattern"]))
assert live_files == [], [str(p) for p in live_files]

for obj in [taxonomy, status, corpus, validator, docket]:
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

for obj in [taxonomy, status, corpus, validator, docket]:
    assert obj["admission_request_count"] == 0, obj.get("object_type")

assert taxonomy["release_candidate_ready"] is False
assert status["release_candidate_ready"] is False

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == taxonomy["current_state"]
assert case["current_state"] == taxonomy["current_state"]
assert registry["current_active_state"] == taxonomy["current_state"]

text = Path("AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.md").read_text(encoding="utf-8")
for needle in [
    "canonical_rejection_reason_count=9",
    "covered_rejection_reason_count=5",
    "uncovered_rejection_reason_count=4",
    "taxonomy_complete_for_current_validator=true",
    "corpus_complete_for_required_reasons=true",
    "admission_request_count=0",
    "authority_satisfied=false",
    "may_advance_now=false",
    "issued=false",
    "media_present=false"
]:
    assert needle in text, needle

print("CINEMATICUM AUTHORITY OBJECT ADMISSION REJECTION TAXONOMY: PASS")
print("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("CANONICAL_REJECTION_REASON_COUNT=9")
print("COVERED_REJECTION_REASON_COUNT=5")
print("UNCOVERED_REJECTION_REASON_COUNT=4")
print("TAXONOMY_COMPLETE_FOR_CURRENT_VALIDATOR=true")
print("CORPUS_COMPLETE_FOR_REQUIRED_REASONS=true")
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
