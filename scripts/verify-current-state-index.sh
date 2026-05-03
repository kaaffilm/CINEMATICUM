#!/usr/bin/env bash
set -euo pipefail

test -f CURRENT_STATE_INDEX_LAW.json
test -f CINEMATICUM_CURRENT_STATE_INDEX.json
test -f CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json
test -f CASES/CASE_001_THE_LAST_RENDER/STATE_SURFACE_CLASSIFICATION.md

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CURRENT_STATE_INDEX_LAW.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

assert law["one_active_truth_per_case"] is True
assert index["surface_type"] == "ACTIVE_CURRENT_STATE"
assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert index["issued_films"] == []
assert index["release_candidate_ready_cases"] == []
assert index["media_admitted_cases"] == []
assert index["outsider_replay_passed_cases"] == []

assert case["surface_type"] == "ACTIVE_CURRENT_STATE"
assert case["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert case["release_candidate_ready"] is False
assert case["issued"] is False
assert case["media_present"] is False
assert case["outsider_replay_passed"] is False

for file in case["prior_layer_status_files"]:
    layer = load(file)
    assert layer["surface_type"] == "LAYER_STATUS_RECORD", file
    assert layer["current_truth_owner"] is False, file
    assert layer["does_not_outrank_current_state_index"] is True, file
    assert layer["does_not_assert_issuance"] is True, file
    assert layer["does_not_admit_media"] is True, file
    assert layer["does_not_assert_replay_pass"] is True, file

active = []
for path in Path("CASES").rglob("*.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("case_id") == "CASE_001_THE_LAST_RENDER" and data.get("surface_type") == "ACTIVE_CURRENT_STATE":
        active.append(str(path))

assert active == ["CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"], active

print("CINEMATICUM CURRENT STATE INDEX: PASS")
print("CASE_001=THE_LAST_RENDER")
print("ACTIVE_CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("REPLAY_PASSED=false")
print("ONE_ACTIVE_CASE_STATE=true")
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
