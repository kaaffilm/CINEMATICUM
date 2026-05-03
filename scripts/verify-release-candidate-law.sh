#!/usr/bin/env bash
set -euo pipefail

test -f RELEASE_CANDIDATE_OBJECT_LAW.json
test -f RELEASE_MANIFEST_SCHEMA.json
test -f MEDIA_HASH_MANIFEST_SCHEMA.json
test -f OUTSIDER_REPLAY_REQUIREMENTS.json
test -f CASES/CASE_001_THE_LAST_RENDER/RELEASE_CANDIDATE_STATUS.json
test -f CASES/CASE_001_THE_LAST_RENDER/LOCKED_PICTURE_BOUNDARY.md

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("RELEASE_CANDIDATE_OBJECT_LAW.json")
release_manifest = load("RELEASE_MANIFEST_SCHEMA.json")
hash_manifest = load("MEDIA_HASH_MANIFEST_SCHEMA.json")
replay = load("OUTSIDER_REPLAY_REQUIREMENTS.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/RELEASE_CANDIDATE_STATUS.json")

assert law["object_type"] == "CINEMATICUM_RELEASE_CANDIDATE_OBJECT_LAW"
assert law["law_boundary"] == "RELEASE_CANDIDATE_OBJECT_LAW_ONLY"
assert law["issued_film"] is False
assert law["media_present"] is False
assert law["generation_present"] is False
assert law["engine_present"] is False
assert law["model_present"] is False
assert law["forbidden_pr3_transition"] == "ISSUED_ADMISSIBLE_MOTION_PICTURE"

assert release_manifest["object_type"] == "CINEMATICUM_RELEASE_MANIFEST_SCHEMA"
assert release_manifest["boundary"] == "SCHEMA_ONLY_NO_RELEASE_ARTIFACT"
assert "raw_media_blob" in release_manifest["forbidden_fields"]
assert "private_key" in release_manifest["forbidden_fields"]

assert hash_manifest["object_type"] == "CINEMATICUM_MEDIA_HASH_MANIFEST_SCHEMA"
assert hash_manifest["boundary"] == "HASH_SCHEMA_ONLY_NO_MEDIA"
assert hash_manifest["hash_algorithm"] == "sha256"
assert "media bytes" in hash_manifest["forbidden_material"]

assert replay["object_type"] == "CINEMATICUM_OUTSIDER_REPLAY_REQUIREMENTS"
assert replay["private_access_required"] is False
assert replay["issued_film"] is False
assert replay["media_present"] is False

assert case["case_id"] == "CASE_001_THE_LAST_RENDER"
assert case["current_state"] == "RELEASE_CANDIDATE_LAW_DECLARED"
assert case["release_candidate_ready"] is False
assert case["issued"] is False
assert case["media_present"] is False
assert case["outsider_replay_passed"] is False

print("CINEMATICUM RELEASE CANDIDATE LAW: PASS")
print("CASE_001=THE_LAST_RENDER")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("SCHEMA_ONLY=true")
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
