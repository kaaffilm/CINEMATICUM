#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_PUBLIC_PERIMETER_SENTINEL_LAW.json
test -f CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json
test -f PUBLIC_PERIMETER_SENTINEL.md
test -f CASES/CASE_001_THE_LAST_RENDER/PUBLIC_PERIMETER_SENTINEL_STATUS.json

FORBIDDEN_PRIVATE_FILES="$(find . -type f \
  \( -iname '.env' -o -iname '.env.*' -o -iname '*.pem' -o -iname '*.key' -o -iname '*.p12' -o -iname '*.pfx' -o -iname '*token*' -o -iname '*secret*' -o -iname '*credential*' \) \
  -not -path './.git/*' | sort || true)"

if test -n "$FORBIDDEN_PRIVATE_FILES"; then
  printf "forbidden private file found:\n%s\n" "$FORBIDDEN_PRIVATE_FILES" >&2
  exit 1
fi

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

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL_LAW.json")
sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/PUBLIC_PERIMETER_SENTINEL_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")
seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
dossier = load("PUBLIC_INSPECTION_DOSSIER.json")
negative = load("PUBLIC_INSPECTION_NEGATIVE_PROOF.json")
precedence = load("CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json")
gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
rejection = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")

assert law["object_type"] == "CINEMATICUM_PUBLIC_PERIMETER_SENTINEL_LAW"
assert law["sentinel_owner"] == "CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json"
assert law["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"

expected_status = {
    "private_access_required": False,
    "media_or_model_payload_present": False,
    "forbidden_private_file_present": False,
    "valid_transition_attempt_present": False,
    "may_advance_now": False,
    "required_authority_objects_missing": True,
    "object_registry_fresh_required": True,
    "verify_all_required": True,
}
for key, expected in expected_status.items():
    assert law["public_perimeter_must_assert"][key] is expected, key

for key, expected in law["currently_false_claims"].items():
    assert expected is False, key

assert sentinel["object_type"] == "CINEMATICUM_PUBLIC_PERIMETER_SENTINEL"
assert sentinel["surface_type"] == "PUBLIC_PERIMETER_SENTINEL"
assert sentinel["case_id"] == "CASE_001_THE_LAST_RENDER"
assert sentinel["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
assert sentinel["current_truth_owner"] is False

for path in sentinel["public_inspection_chain"] + sentinel["machine_truth_chain"] + sentinel["required_verifiers"]:
    assert Path(path).exists(), path

perimeter = sentinel["perimeter_status"]
assert perimeter["private_access_required"] is False
assert perimeter["media_or_model_payload_present"] is False
assert perimeter["forbidden_private_file_present"] is False
assert perimeter["valid_transition_attempt_present"] is False
assert perimeter["invalid_transition_attempt_present"] is False
assert perimeter["transition_attempts_recorded"] == 0
assert perimeter["may_advance_now"] is False
assert perimeter["required_authority_objects_missing"] is True
assert perimeter["schemas_do_not_satisfy_authority_objects"] is True
assert perimeter["object_registry_fresh_required"] is True
assert perimeter["verify_all_required"] is True

assert status["object_type"] == "CINEMATICUM_CASE_PUBLIC_PERIMETER_SENTINEL_STATUS"
assert status["surface_type"] == "LAYER_STATUS_RECORD"
assert status["current_truth_owner"] is False

for key in [
    "private_access_required",
    "media_or_model_payload_present",
    "forbidden_private_file_present",
    "valid_transition_attempt_present",
    "invalid_transition_attempt_present",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present",
    "generation_present",
    "engine_present",
    "model_present",
    "outsider_replay_passed",
    "admissibility_verdict_present",
    "terminal_closure_present"
]:
    assert status[key] is False, key

assert status["transition_attempts_recorded"] == 0
assert status["required_authority_objects_missing"] is True

current = sentinel["current_state"]
assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == current
assert case["current_state"] == current
assert registry["current_active_state"] == current
assert seal["current_state"] == current
assert dossier["current_state"] == current
assert negative["current_state"] == current
assert precedence["current_state"] == current
assert gate["current_state"] == current
assert checklist["current_state"] == current
assert rejection["current_state"] == current

assert gate["may_advance_now"] is False
assert checklist["required_authority_objects_missing"] is True
assert rejection["valid_transition_attempt_present"] is False
assert rejection["attempt_counts"]["recorded"] == 0

for key in [
    "release_candidate_ready",
    "issued",
    "media_present",
    "generation_present",
    "engine_present",
    "model_present",
    "outsider_replay_passed",
    "admissibility_verdict_present",
    "terminal_closure_present"
]:
    assert sentinel["current_false_values"][key] is False, key

forbidden = set(sentinel["forbidden_transition_attempt_object_types"])
present = {}
for path in Path(".").rglob("*.json"):
    if ".git" in path.parts:
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    object_type = data.get("object_type")
    if object_type:
        present.setdefault(object_type, []).append(path.as_posix())

for object_type in forbidden:
    assert object_type not in present, (object_type, present.get(object_type))

text = Path("PUBLIC_PERIMETER_SENTINEL.md").read_text(encoding="utf-8")
for needle in [
    "private_access_required=false",
    "media_or_model_payload_present=false",
    "forbidden_private_file_present=false",
    "valid_transition_attempt_present=false",
    "transition_attempts_recorded=0",
    "may_advance_now=false",
    "required_authority_objects_missing=true",
    "object_registry_fresh_required=true",
    "verify_all_required=true",
    "raw media",
    "model weights",
    "does not issue a film",
    "does not admit media"
]:
    assert needle in text, needle

print("CINEMATICUM PUBLIC PERIMETER SENTINEL: PASS")
print("CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
print("PRIVATE_ACCESS_REQUIRED=false")
print("MEDIA_OR_MODEL_PAYLOAD_PRESENT=false")
print("FORBIDDEN_PRIVATE_FILE_PRESENT=false")
print("VALID_TRANSITION_ATTEMPT_PRESENT=false")
print("MAY_ADVANCE_NOW=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
