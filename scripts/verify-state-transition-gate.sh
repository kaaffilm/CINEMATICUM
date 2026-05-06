#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_STATE_TRANSITION_GATE_LAW.json
test -f CINEMATICUM_STATE_TRANSITION_GATE.json
test -f STATE_TRANSITION_GATE.md
test -f CASES/CASE_001_THE_LAST_RENDER/STATE_TRANSITION_GATE_STATUS.json

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_STATE_TRANSITION_GATE_LAW.json")
gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/STATE_TRANSITION_GATE_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
matrix = load("CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json")
precedence = load("CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json")
seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
negative = load("PUBLIC_INSPECTION_NEGATIVE_PROOF.json")

assert law["object_type"] == "CINEMATICUM_STATE_TRANSITION_GATE_LAW"
assert law["transition_gate_owner"] == "CINEMATICUM_STATE_TRANSITION_GATE.json"
assert law["current_state_owner"] == "CINEMATICUM_CURRENT_STATE_INDEX.json"
assert law["case_current_state_owner"] == "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"
assert law["progression_owner"] == "CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json"
assert law["authority_precedence_owner"] == "CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json"
assert law["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
assert "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS" in law["blocked_targets"]
assert "ISSUED_ADMISSIBLE_MOTION_PICTURE" in law["blocked_targets"]

for key, expected in law["currently_false_claims"].items():
    assert expected is False, key

for forbidden in [
    "current state advanced by README prose",
    "current state advanced by schema object",
    "current state advanced by object registry projection",
    "current state advanced by repository status seal",
    "current state advanced by public inspection surface",
    "current state advanced by negative proof",
    "current state advanced by layer-status record"
]:
    assert forbidden in law["forbidden_transition_conditions"], forbidden

assert gate["object_type"] == "CINEMATICUM_STATE_TRANSITION_GATE"
assert gate["surface_type"] == "STATE_TRANSITION_GATE"
assert gate["case_id"] == "CASE_001_THE_LAST_RENDER"
assert gate["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
assert gate["current_state_is_authoritative"] is False
assert gate["gate_status"] == "BLOCKED_FOR_ADVANCEMENT"
assert gate["may_advance_now"] is False
assert gate["next_candidate_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
assert gate["next_candidate_state_unblocked"] is False
assert gate["final_issuance_state_unblocked"] is False

transitions = {(t["from"], t["to"]): t for t in gate["transition_candidates"]}
assert ("REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS") in transitions
assert ("REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", "ISSUED_ADMISSIBLE_MOTION_PICTURE") in transitions
for transition in transitions.values():
    assert transition["status"] == "blocked"
    assert transition["missing_required_authority_objects"], transition

for required in [
    "DIRECTOR_ACCEPTANCE_OBJECT",
    "FINAL_CUT_TIMELINE_LOCK_OBJECT",
    "MEDIA_HASH_MANIFEST_OBJECT",
    "ADMISSIBILITY_VERDICT_OBJECT",
    "TERMINAL_CLOSURE_CANDIDATE_OBJECT"
]:
    assert required in transitions[("REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")]["missing_required_authority_objects"], required

for required in [
    "MOTION_PICTURE_ISSUANCE_ACT_OBJECT",
    "OUTSIDER_REPLAY_PASS_OBJECT",
    "ADMISSIBILITY_VERDICT_OBJECT",
    "TERMINAL_CLOSURE_OBJECT",
    "MEDIA_ADMISSION_OBJECT"
]:
    assert required in transitions[("REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", "ISSUED_ADMISSIBLE_MOTION_PICTURE")]["missing_required_authority_objects"], required

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
    assert gate["current_false_values"][key] is False, key
    assert status[key] is False, key

assert status["object_type"] == "CINEMATICUM_CASE_STATE_TRANSITION_GATE_STATUS"
assert status["surface_type"] == "LAYER_STATUS_RECORD"
assert status["current_truth_owner"] is False
assert status["may_advance_now"] is False
assert status["release_candidate_ready_unblocked"] is False
assert status["issuance_unblocked"] is False

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == gate["current_state"]
assert case["current_state"] == gate["current_state"]
assert matrix["current_active_state"] == gate["current_state"]
assert precedence["current_state"] == gate["current_state"]
assert seal["current_state"] == gate["current_state"]
assert negative["current_state"] == gate["current_state"]

assert "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS" in matrix["states_not_reached"]
assert "ISSUED_ADMISSIBLE_MOTION_PICTURE" in matrix["states_not_reached"]

text = Path("STATE_TRANSITION_GATE.md").read_text(encoding="utf-8")
for needle in [
    "may_advance_now=false",
    "next_candidate_state=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS",
    "next_candidate_state_unblocked=false",
    "final_issuance_state_unblocked=false",
    "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS",
    "ISSUED_ADMISSIBLE_MOTION_PICTURE",
    "release_candidate_ready=false",
    "issued=false",
    "media_present=false",
    "outsider_replay_passed=false",
    "does not issue a film",
    "does not admit media"
]:
    assert needle in text, needle

print("CINEMATICUM STATE TRANSITION GATE: PASS")
print("CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
print("MAY_ADVANCE_NOW=false")
print("REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS_UNBLOCKED=false")
print("ISSUANCE_UNBLOCKED=false")
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
