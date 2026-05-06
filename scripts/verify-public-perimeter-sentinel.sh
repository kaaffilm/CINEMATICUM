#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json
test -f CINEMATICUM_PUBLIC_PERIMETER_SENTINEL_LAW.json
test -f CASES/CASE_001_THE_LAST_RENDER/PUBLIC_PERIMETER_SENTINEL_STATUS.json

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
CASE = 'CASE_001_THE_LAST_RENDER'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
law = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/PUBLIC_PERIMETER_SENTINEL_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")

assert sentinel["object_type"] == "CINEMATICUM_PUBLIC_PERIMETER_SENTINEL"
assert law["object_type"] == "CINEMATICUM_PUBLIC_PERIMETER_SENTINEL_LAW"
assert status["status"] == "PASS"

for obj in (sentinel, law, status):
    assert obj["case_id"] == CASE
    assert obj["current_state"] == TARGET
    assert obj["private_access_required"] is False
    assert obj["network_required_after_clone"] is False
    assert obj["media_or_model_payload_present"] is False
    assert obj["forbidden_private_file_present"] is False
    assert obj["valid_transition_attempt_present"] is False
    assert obj["release_candidate_ready"] is False
    assert obj["release_candidate_artifacts_bound"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False
    assert obj["admissibility_verdict_present"] is False
    assert obj["terminal_closure_present"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False
    assert obj["next_required_object"] == NEXT_OBJECT

assert sentinel["authority_object_stack_complete"] is True
assert sentinel["accepted_authority_object_count"] == 8
assert sentinel["instantiated_authority_object_count"] == 8
assert sentinel["unfilled_authority_object_slot_count"] == 0

assert index["active_case_states"][CASE] == TARGET
assert case["current_state"] == TARGET
assert gate["current_state"] == TARGET
assert gate["may_advance_now"] is False
assert ledger["current_state"] == TARGET
assert ledger["valid_transition_attempt_present"] is False

print("CINEMATICUM PUBLIC PERIMETER SENTINEL: PASS")
print(f"CURRENT_STATE={TARGET}")
print("PRIVATE_ACCESS_REQUIRED=false")
print("MEDIA_OR_MODEL_PAYLOAD_PRESENT=false")
print("FORBIDDEN_PRIVATE_FILE_PRESENT=false")
print("VALID_TRANSITION_ATTEMPT_PRESENT=false")
print("MAY_ADVANCE_NOW=false")
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
