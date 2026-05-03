#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_REPOSITORY_STATUS_SEAL_LAW.json
test -f CINEMATICUM_REPOSITORY_STATUS_SEAL.json
test -f PUBLIC_STATUS.md

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_REPOSITORY_STATUS_SEAL_LAW.json")
seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
matrix = load("CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert law["object_type"] == "CINEMATICUM_REPOSITORY_STATUS_SEAL_LAW"
assert law["seal_owner"] == "CINEMATICUM_REPOSITORY_STATUS_SEAL.json"
assert law["public_document_owner"] == "PUBLIC_STATUS.md"
assert law["current_state_owner"] == "CINEMATICUM_CURRENT_STATE_INDEX.json"
assert law["case_current_state_owner"] == "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"
assert law["seal_must_assert"]["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert law["seal_must_assert"]["release_candidate_ready"] is False
assert law["seal_must_assert"]["issued"] is False
assert law["seal_must_assert"]["media_present"] is False
assert law["seal_must_assert"]["outsider_replay_passed"] is False
assert law["seal_must_assert"]["verify_all_pass_required"] is True
assert law["seal_must_assert"]["object_registry_fresh_required"] is True

assert seal["object_type"] == "CINEMATICUM_REPOSITORY_STATUS_SEAL"
assert seal["surface_type"] == "REPOSITORY_STATUS_SEAL"
assert seal["seal_is_current_truth_owner"] is False
assert seal["current_truth_owner"] == "CINEMATICUM_CURRENT_STATE_INDEX.json"
assert seal["case_current_truth_owner"] == "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"
assert seal["case_id"] == "CASE_001_THE_LAST_RENDER"
assert seal["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

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
    assert seal[key] is False, key

assert seal["verify_all_pass_required"] is True
assert seal["object_registry_fresh_required"] is True

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == seal["current_state"]
assert case["current_state"] == seal["current_state"]
assert matrix["current_active_state"] == seal["current_state"]
assert registry["current_active_state"] == seal["current_state"]

text = Path("PUBLIC_STATUS.md").read_text(encoding="utf-8")
for needle in [
    "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED",
    "release_candidate_ready=false",
    "issued=false",
    "media_present=false",
    "outsider_replay_passed=false",
    "bash scripts/verify-all.sh",
    "bash scripts/verify-object-registry-fresh.sh",
    "does not issue a film"
]:
    assert needle in text, needle

print("CINEMATICUM REPOSITORY STATUS SEAL: PASS")
print("ACTIVE_CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("REPLAY_PASSED=false")
print("VERIFY_ALL_REQUIRED=true")
print("REGISTRY_FRESH_REQUIRED=true")
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
