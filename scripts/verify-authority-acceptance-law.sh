#!/usr/bin/env bash
set -euo pipefail

CURRENT_STATE="REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
export CURRENT_STATE
test -f AUTHORITY_ACCEPTANCE_OBJECT_LAW.json
test -f DIRECTOR_ACCEPTANCE_OBJECT_SCHEMA.json
test -f FINAL_CUT_TIMELINE_LOCK_SCHEMA.json
test -f SOUND_MIX_LOCK_SCHEMA.json
test -f COLOR_GRADE_LOCK_SCHEMA.json
test -f TERMINAL_CLOSURE_CANDIDATE_SCHEMA.json
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_ACCEPTANCE_STATUS.json
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_ACCEPTANCE_BOUNDARY.md

python3 - <<'PY'
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("AUTHORITY_ACCEPTANCE_OBJECT_LAW.json")
director = load("DIRECTOR_ACCEPTANCE_OBJECT_SCHEMA.json")
timeline = load("FINAL_CUT_TIMELINE_LOCK_SCHEMA.json")
sound = load("SOUND_MIX_LOCK_SCHEMA.json")
grade = load("COLOR_GRADE_LOCK_SCHEMA.json")
closure = load("TERMINAL_CLOSURE_CANDIDATE_SCHEMA.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_ACCEPTANCE_STATUS.json")

assert law["object_type"] == "CINEMATICUM_AUTHORITY_ACCEPTANCE_OBJECT_LAW"
assert law["law_boundary"] == "AUTHORITY_ACCEPTANCE_OBJECT_LAW_ONLY"
assert law["issued_film"] is False
assert law["release_candidate_ready"] is False
assert law["media_present"] is False
assert law["generation_present"] is False
assert law["engine_present"] is False
assert law["model_present"] is False
assert law["pr4_state_transition"]["not_to"] == "RELEASE_CANDIDATE_READY"

for obj, expected_type, expected_boundary in [
    (director, "CINEMATICUM_DIRECTOR_ACCEPTANCE_OBJECT_SCHEMA", "SCHEMA_ONLY_NO_ACCEPTANCE_OBJECT"),
    (timeline, "CINEMATICUM_FINAL_CUT_TIMELINE_LOCK_SCHEMA", "SCHEMA_ONLY_NO_TIMELINE_OBJECT"),
    (sound, "CINEMATICUM_SOUND_MIX_LOCK_SCHEMA", "SCHEMA_ONLY_NO_AUDIO_OBJECT"),
    (grade, "CINEMATICUM_COLOR_GRADE_LOCK_SCHEMA", "SCHEMA_ONLY_NO_IMAGE_OBJECT"),
    (closure, "CINEMATICUM_TERMINAL_CLOSURE_CANDIDATE_SCHEMA", "SCHEMA_ONLY_NO_TERMINAL_CLOSURE")
]:
    assert obj["object_type"] == expected_type
    assert obj["boundary"] == expected_boundary

assert "embedded_media" in director["forbidden_fields"]
assert "raw_video" in timeline["forbidden_fields"]
assert "raw_audio" in sound["forbidden_fields"]
assert "raw_image" in grade["forbidden_fields"]
assert "media_bytes" in closure["forbidden_fields"]

assert case["case_id"] == "CASE_001_THE_LAST_RENDER"
assert case["current_state"] == "AUTHORITY_ACCEPTANCE_LAW_DECLARED"
assert case["release_candidate_ready"] is False
assert case["issued"] is False
assert case["media_present"] is False
assert case["director_acceptance_present"] is False
assert case["timeline_lock_present"] is False
assert case["terminal_closure_candidate_present"] is False

print("CINEMATICUM AUTHORITY ACCEPTANCE LAW: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("CASE_001=THE_LAST_RENDER")
print("AUTHORITY_ACCEPTANCE_LAW_DECLARED=true")
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
