#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST_LAW.json
test -f CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json
test -f REQUIRED_AUTHORITY_OBJECTS.md
test -f CASES/CASE_001_THE_LAST_RENDER/REQUIRED_AUTHORITY_OBJECTS_STATUS.json

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST_LAW.json")
checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/REQUIRED_AUTHORITY_OBJECTS_STATUS.json")
gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
precedence = load("CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert law["object_type"] == "CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST_LAW"
assert law["checklist_owner"] == "CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json"
assert law["transition_gate_owner"] == "CINEMATICUM_STATE_TRANSITION_GATE.json"
assert law["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"

for key, expected in law["checklist_must_assert"].items():
    assert expected is (True if key in ["required_authority_objects_missing", "schemas_do_not_satisfy_authority_objects"] else False), key

for key, expected in law["currently_false_claims"].items():
    assert expected is False, key

for forbidden in [
    "README prose",
    "schema object",
    "object registry entry",
    "repository status seal",
    "state transition gate row",
    "checklist row",
    "layer-status record"
]:
    assert forbidden in law["forbidden_satisfiers"], forbidden

assert checklist["object_type"] == "CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST"
assert checklist["surface_type"] == "REQUIRED_AUTHORITY_OBJECT_CHECKLIST"
assert checklist["case_id"] == "CASE_001_THE_LAST_RENDER"
assert checklist["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
assert checklist["current_truth_owner"] is False
assert checklist["schemas_do_not_satisfy_authority_objects"] is True
assert checklist["may_advance_now"] is False
assert checklist["release_candidate_ready_unblocked"] is False
assert checklist["issuance_unblocked"] is False
assert checklist["required_authority_objects_missing"] is True

release_required = {
    item["required_object_type"]: item
    for item in checklist["required_for_release_candidate_ready"]
}
issuance_required = {
    item["required_object_type"]: item
    for item in checklist["required_for_issued_admissible_motion_picture"]
}

gate_release_missing = set()
gate_issuance_missing = set()
for transition in gate["transition_candidates"]:
    if transition["to"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS":
        gate_release_missing.update(transition["missing_required_authority_objects"])
    if transition["to"] == "ISSUED_ADMISSIBLE_MOTION_PICTURE":
        gate_issuance_missing.update(transition["missing_required_authority_objects"])

assert set(release_required) == gate_release_missing
assert set(issuance_required) == gate_issuance_missing

for collection in [release_required, issuance_required]:
    for required_type, item in collection.items():
        assert item["status"] == "missing", required_type
        if item["schema_available"] is True:
            assert item["schema_path"], required_type
            assert Path(item["schema_path"]).exists(), item["schema_path"]

all_required_types = set(release_required) | set(issuance_required)

object_types_in_repo = {}
for path in Path(".").rglob("*.json"):
    if ".git" in path.parts:
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    object_type = data.get("object_type")
    if object_type:
        object_types_in_repo.setdefault(object_type, []).append(path.as_posix())

for required_type in all_required_types:
    # Schema objects may exist, but exact required authority objects must not.
    assert required_type not in object_types_in_repo, (required_type, object_types_in_repo.get(required_type))

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
    assert checklist["current_false_values"][key] is False, key
    assert status[key] is False, key

assert status["object_type"] == "CINEMATICUM_CASE_REQUIRED_AUTHORITY_OBJECTS_STATUS"
assert status["surface_type"] == "LAYER_STATUS_RECORD"
assert status["current_truth_owner"] is False
assert status["may_advance_now"] is False
assert status["release_candidate_ready_unblocked"] is False
assert status["issuance_unblocked"] is False
assert status["required_authority_objects_missing"] is True
assert status["schemas_do_not_satisfy_authority_objects"] is True

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == checklist["current_state"]
assert case["current_state"] == checklist["current_state"]
assert gate["current_state"] == checklist["current_state"]
assert precedence["current_state"] == checklist["current_state"]
assert registry["current_active_state"] == checklist["current_state"]

text = Path("REQUIRED_AUTHORITY_OBJECTS.md").read_text(encoding="utf-8")
for needle in [
    "may_advance_now=false",
    "release_candidate_ready_unblocked=false",
    "issuance_unblocked=false",
    "required_authority_objects_missing=true",
    "schemas_do_not_satisfy_authority_objects=true",
    "DIRECTOR_ACCEPTANCE_OBJECT",
    "FINAL_CUT_TIMELINE_LOCK_OBJECT",
    "MEDIA_HASH_MANIFEST_OBJECT",
    "MOTION_PICTURE_ISSUANCE_ACT_OBJECT",
    "OUTSIDER_REPLAY_PASS_OBJECT",
    "ADMISSIBILITY_VERDICT_OBJECT",
    "TERMINAL_CLOSURE_OBJECT",
    "MEDIA_ADMISSION_OBJECT",
    "A schema does not satisfy an authority object",
    "does not issue a film",
    "does not admit media"
]:
    assert needle in text, needle

print("CINEMATICUM REQUIRED AUTHORITY OBJECT CHECKLIST: PASS")
print("CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
print("MAY_ADVANCE_NOW=false")
print("REQUIRED_AUTHORITY_OBJECTS_MISSING=true")
print("SCHEMAS_DO_NOT_SATISFY_AUTHORITY_OBJECTS=true")
print("REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS=false")
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
