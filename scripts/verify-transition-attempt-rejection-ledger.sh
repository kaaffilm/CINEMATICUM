#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LAW.json
test -f CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json
test -f TRANSITION_ATTEMPT_REJECTION_LEDGER.md
test -f CASES/CASE_001_THE_LAST_RENDER/TRANSITION_ATTEMPT_REJECTION_STATUS.json

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LAW.json")
ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/TRANSITION_ATTEMPT_REJECTION_STATUS.json")
gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
precedence = load("CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert law["object_type"] == "CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LAW"
assert law["ledger_owner"] == "CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json"
assert law["transition_gate_owner"] == "CINEMATICUM_STATE_TRANSITION_GATE.json"
assert law["required_authority_object_checklist_owner"] == "CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json"
assert law["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
assert law["attempts_recorded"] == 0
assert law["attempts_accepted"] == 0
assert law["attempts_rejected"] == 0
assert law["valid_transition_attempt_present"] is False
assert law["invalid_transition_attempt_present"] is False

for target in ["REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", "ISSUED_ADMISSIBLE_MOTION_PICTURE"]:
    assert target in law["blocked_targets"], target

for key, expected in law["currently_false_claims"].items():
    assert expected is False, key

assert ledger["object_type"] == "CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER"
assert ledger["surface_type"] == "TRANSITION_ATTEMPT_REJECTION_LEDGER"
assert ledger["case_id"] == "CASE_001_THE_LAST_RENDER"
assert ledger["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
assert ledger["current_truth_owner"] is False
assert ledger["may_advance_now"] is False
assert ledger["required_authority_objects_missing"] is True
assert ledger["schemas_do_not_satisfy_authority_objects"] is True
assert ledger["valid_transition_attempt_present"] is False
assert ledger["invalid_transition_attempt_present"] is False
assert ledger["attempt_counts"] == {"recorded": 0, "accepted": 0, "rejected": 0}
assert ledger["transition_attempt_records"] == []

rules = {rule["target_state"]: rule for rule in ledger["automatic_rejection_rules"]}
assert set(rules) == {"REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", "ISSUED_ADMISSIBLE_MOTION_PICTURE"}
for rule in rules.values():
    assert rule["would_be_rejected_now"] is True
    assert "blocked" in rule["reason"] or "missing" in rule["reason"]

assert status["object_type"] == "CINEMATICUM_CASE_TRANSITION_ATTEMPT_REJECTION_STATUS"
assert status["surface_type"] == "LAYER_STATUS_RECORD"
assert status["current_truth_owner"] is False
assert status["transition_attempts_recorded"] == 0
assert status["transition_attempts_accepted"] == 0
assert status["transition_attempts_rejected"] == 0
assert status["valid_transition_attempt_present"] is False
assert status["invalid_transition_attempt_present"] is False
assert status["may_advance_now"] is False
assert status["required_authority_objects_missing"] is True
assert status["release_candidate_ready_unblocked"] is False
assert status["issuance_unblocked"] is False

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
    assert ledger["current_false_values"][key] is False, key
    assert status[key] is False, key

assert gate["current_state"] == ledger["current_state"]
assert gate["may_advance_now"] is False
assert gate["next_candidate_state_unblocked"] is False
assert gate["final_issuance_state_unblocked"] is False
assert checklist["current_state"] == ledger["current_state"]
assert checklist["required_authority_objects_missing"] is True
assert checklist["may_advance_now"] is False
assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == ledger["current_state"]
assert case["current_state"] == ledger["current_state"]
assert precedence["current_state"] == ledger["current_state"]
assert registry["current_active_state"] == ledger["current_state"]

forbidden = set(ledger["forbidden_attempt_object_types"])
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

text = Path("TRANSITION_ATTEMPT_REJECTION_LEDGER.md").read_text(encoding="utf-8")
for needle in [
    "transition_attempts_recorded=0",
    "transition_attempts_accepted=0",
    "transition_attempts_rejected=0",
    "valid_transition_attempt_present=false",
    "invalid_transition_attempt_present=false",
    "may_advance_now=false",
    "required_authority_objects_missing=true",
    "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS",
    "ISSUED_ADMISSIBLE_MOTION_PICTURE",
    "CINEMATICUM_STATE_TRANSITION_ATTEMPT",
    "release_candidate_ready=false",
    "issued=false",
    "media_present=false",
    "does not issue a film",
    "does not admit media"
]:
    assert needle in text, needle

print("CINEMATICUM TRANSITION ATTEMPT REJECTION LEDGER: PASS")
print("CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
print("TRANSITION_ATTEMPTS_RECORDED=0")
print("VALID_TRANSITION_ATTEMPT_PRESENT=false")
print("MAY_ADVANCE_NOW=false")
print("REQUIRED_AUTHORITY_OBJECTS_MISSING=true")
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
