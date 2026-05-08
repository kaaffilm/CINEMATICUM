#!/usr/bin/env bash
set -euo pipefail

test -f OUTSIDER_CLONE_REPLAY.json
test -f CINEMATICUM_OUTSIDER_CLONE_REPLAY.json
test -f OUTSIDER_CLONE_REPLAY_LAW.json
test -f CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_CLONE_REPLAY_STATUS.json

python3 - <<'PY2'
import json
from pathlib import Path

RECORD_TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
ACTIVE_TARGET = 'RELEASE_CANDIDATE_READY'
CASE = 'CASE_001_THE_LAST_RENDER'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

clone = load("OUTSIDER_CLONE_REPLAY.json")
cin_clone = load("CINEMATICUM_OUTSIDER_CLONE_REPLAY.json")
law = load("OUTSIDER_CLONE_REPLAY_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_CLONE_REPLAY_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert clone == cin_clone
assert clone["object_type"] == "CINEMATICUM_OUTSIDER_CLONE_REPLAY"
assert law["object_type"] == "CINEMATICUM_OUTSIDER_CLONE_REPLAY_LAW"
assert status["status"] == "PASS"

for obj in (clone, law, status):
    assert obj["case_id"] == CASE
    assert obj["current_state"] == RECORD_TARGET
    assert obj["fresh_checkout_can_verify"] is True
    assert obj["private_access_required"] is False
    assert obj["network_required_after_clone"] is False
    assert obj["media_or_model_payload_present"] is False
    assert obj["forbidden_private_file_present"] is False
    assert obj["valid_transition_attempt_present"] is False

    # Non-capability / non-issuance guarantees remain false.
    assert obj["release_candidate_ready"] is False
    assert obj["release_candidate_artifacts_bound"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False

    # Post-advancement repositories may carry later proof flags elsewhere;
    # this replay object is still a historical non-advancing proof surface.
    assert obj["authority_object_stack_complete"] is True
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["next_required_object"] == NEXT_OBJECT

assert index["active_case_states"][CASE] == ACTIVE_TARGET
assert case["current_state"] == ACTIVE_TARGET
assert registry["current_active_state"] == ACTIVE_TARGET

assert sentinel["private_access_required"] is False
if "active_current_state" in sentinel:
    assert sentinel["active_current_state"] == ACTIVE_TARGET

print("CINEMATICUM OUTSIDER CLONE REPLAY: PASS")
print(f"CURRENT_STATE={RECORD_TARGET}")
print(f"ACTIVE_CURRENT_STATE={ACTIVE_TARGET}")
print("FRESH_CHECKOUT_CAN_VERIFY=true")
print("PRIVATE_ACCESS_REQUIRED=false")
print("NETWORK_REQUIRED_AFTER_CLONE=false")
print("MEDIA_OR_MODEL_PAYLOAD_PRESENT=false")
print("VALID_TRANSITION_ATTEMPT_PRESENT=false")
print("RELEASE_CANDIDATE_READY=false")
print("ACTIVE_RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2

MEDIA_OR_MODEL="$(find . -type f \
  \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.avi' -o -iname '*.mkv' -o -iname '*.webm' \
     -o -iname '*.wav' -o -iname '*.aiff' -o -iname '*.flac' -o -iname '*.mp3' \
     -o -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.tiff' -o -iname '*.exr' -o -iname '*.dpx' \
     -o -iname '*.pt' -o -iname '*.pth' -o -iname '*.ckpt' -o -iname '*.safetensors' -o -iname '*.onnx' \) \
  -not -path './.git/*' \
  -not -path './cinematicum_closed_pr_dig/*' \
  -print -quit)"

test -z "$MEDIA_OR_MODEL"
