#!/usr/bin/env bash
set -euo pipefail

test -f PUBLIC_INSPECTION_NEGATIVE_PROOF_LAW.json
test -f PUBLIC_INSPECTION_NEGATIVE_PROOF.json
test -f PUBLIC_NEGATIVE_PROOF.md
test -f CASES/CASE_001_THE_LAST_RENDER/PUBLIC_NEGATIVE_PROOF_STATUS.json

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("PUBLIC_INSPECTION_NEGATIVE_PROOF_LAW.json")
proof = load("PUBLIC_INSPECTION_NEGATIVE_PROOF.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/PUBLIC_NEGATIVE_PROOF_STATUS.json")
dossier = load("PUBLIC_INSPECTION_DOSSIER.json")
seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
matrix = load("CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json")

assert law["object_type"] == "CINEMATICUM_PUBLIC_INSPECTION_NEGATIVE_PROOF_LAW"
assert law["negative_proof_owner"] == "PUBLIC_INSPECTION_NEGATIVE_PROOF.json"
assert law["public_document_owner"] == "PUBLIC_NEGATIVE_PROOF.md"
assert law["inspection_dossier_owner"] == "PUBLIC_INSPECTION_DOSSIER.json"
assert law["status_seal_owner"] == "CINEMATICUM_REPOSITORY_STATUS_SEAL.json"

for key, expected in law["must_remain_false"].items():
    assert expected is False, key

assert proof["object_type"] == "CINEMATICUM_PUBLIC_INSPECTION_NEGATIVE_PROOF"
assert proof["surface_type"] == "NEGATIVE_PROOF"
assert proof["case_id"] == "CASE_001_THE_LAST_RENDER"
assert proof["current_state"] == "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"

for key, proves_absence in proof["proves_absence_of"].items():
    assert proves_absence is True, key
    assert proof["current_false_values"][key] is False, key

for absent in [
    "MOTION_PICTURE_ISSUANCE_ACT_OBJECT",
    "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS_OBJECT",
    "OUTSIDER_REPLAY_PASS_OBJECT",
    "ADMISSIBILITY_VERDICT_OBJECT",
    "TERMINAL_CLOSURE_OBJECT",
    "MEDIA_ADMISSION_OBJECT"
]:
    assert absent in proof["required_absent_authority_objects"]

assert status["object_type"] == "CINEMATICUM_CASE_PUBLIC_NEGATIVE_PROOF_STATUS"
assert status["surface_type"] == "LAYER_STATUS_RECORD"
assert status["current_truth_owner"] is False
assert status["negative_proof_present"] is True

for key in [
    "release_candidate_ready",
    "issued",
    "media_present",
    "generation_present",
    "engine_present",
    "model_present",
    "outsider_replay_passed",
    "admissibility_verdict_present",
    "terminal_closure_present",
]:
    assert status[key] is False, key
    assert dossier["expected_current_claims"][key] is False, key
    if key in seal:
        assert seal[key] is False, key
    if key in case:
        assert case[key] is False, key
    if key in matrix["currently_false_claims"]:
        assert matrix["currently_false_claims"][key] is False, key

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == proof["current_state"]
assert case["current_state"] == proof["current_state"]
assert seal["current_state"] == proof["current_state"]
assert dossier["current_state"] == proof["current_state"]

text = Path("PUBLIC_NEGATIVE_PROOF.md").read_text(encoding="utf-8")
for needle in [
    "does not issue a film",
    "does not make the case release-candidate-ready",
    "does not admit media",
    "does not execute replay",
    "does not prove replay passed",
    "does not produce an admissibility verdict",
    "does not create terminal closure",
    "release_candidate_ready=false",
    "issued=false",
    "media_present=false",
    "outsider_replay_passed=false"
]:
    assert needle in text, needle

print("CINEMATICUM PUBLIC INSPECTION NEGATIVE PROOF: PASS")
print("ISSUED=false")
print("REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS=false")
print("MEDIA_PRESENT=false")
print("REPLAY_PASSED=false")
print("VERDICT_PRESENT=false")
print("TERMINAL_CLOSURE=false")
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
