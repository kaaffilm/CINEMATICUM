#!/usr/bin/env bash
set -euo pipefail

test -f OUTSIDER_REPLAY_BUNDLE_OBJECT_LAW.json
test -f OUTSIDER_REPLAY_BUNDLE_SCHEMA.json
test -f REPLAY_EXECUTION_REPORT_SCHEMA.json
test -f ADMISSIBILITY_VERDICT_SCHEMA.json
test -f PUBLIC_REPLAY_INDEX_SCHEMA.json
test -f CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_REPLAY_BUNDLE_STATUS.json
test -f CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_REPLAY_BUNDLE_BOUNDARY.md

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("OUTSIDER_REPLAY_BUNDLE_OBJECT_LAW.json")
bundle = load("OUTSIDER_REPLAY_BUNDLE_SCHEMA.json")
report = load("REPLAY_EXECUTION_REPORT_SCHEMA.json")
verdict = load("ADMISSIBILITY_VERDICT_SCHEMA.json")
index = load("PUBLIC_REPLAY_INDEX_SCHEMA.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_REPLAY_BUNDLE_STATUS.json")

assert law["object_type"] == "CINEMATICUM_OUTSIDER_REPLAY_BUNDLE_OBJECT_LAW"
assert law["law_boundary"] == "OUTSIDER_REPLAY_BUNDLE_OBJECT_LAW_ONLY"
assert law["issued_film"] is False
assert law["release_candidate_ready"] is False
assert law["outsider_replay_passed"] is False
assert law["media_present"] is False
assert law["generation_present"] is False
assert law["engine_present"] is False
assert law["model_present"] is False
assert "actual replay pass" in law["forbidden_pr5_outputs"]
assert "ISSUED_ADMISSIBLE_MOTION_PICTURE" in law["pr5_state_transition"]["not_to"]

assert bundle["object_type"] == "CINEMATICUM_OUTSIDER_REPLAY_BUNDLE_SCHEMA"
assert bundle["boundary"] == "SCHEMA_ONLY_NO_REPLAY_BUNDLE"
assert bundle["private_access_required"] is False
assert "embedded_media" in bundle["forbidden_fields"]
assert "bundle_does_not_issue_film" in bundle["required_assertions"]

assert report["object_type"] == "CINEMATICUM_REPLAY_EXECUTION_REPORT_SCHEMA"
assert report["boundary"] == "SCHEMA_ONLY_NO_REPLAY_EXECUTION"
assert "digest_match_check" in report["required_checks"]
assert "media_bytes" in report["forbidden_fields"]

assert verdict["object_type"] == "CINEMATICUM_ADMISSIBILITY_VERDICT_SCHEMA"
assert verdict["boundary"] == "SCHEMA_ONLY_NO_VERDICT"
assert "ADMISSIBLE" in verdict["allowed_verdicts"]
assert "UNRESOLVED" in verdict["allowed_verdicts"]
assert "unbounded_ai_judgment" in verdict["forbidden_fields"]

assert index["object_type"] == "CINEMATICUM_PUBLIC_REPLAY_INDEX_SCHEMA"
assert index["boundary"] == "SCHEMA_ONLY_NO_PUBLIC_INDEX"
assert "index_requires_no_private_access" in index["required_assertions"]
assert "media_bytes" in index["forbidden_fields"]

assert case["case_id"] == "CASE_001_THE_LAST_RENDER"
assert case["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert case["release_candidate_ready"] is False
assert case["issued"] is False
assert case["media_present"] is False
assert case["outsider_replay_bundle_present"] is False
assert case["replay_execution_report_present"] is False
assert case["admissibility_verdict_present"] is False
assert case["outsider_replay_passed"] is False

print("CINEMATICUM OUTSIDER REPLAY BUNDLE LAW: PASS")
print("CASE_001=THE_LAST_RENDER")
print("OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED=true")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("REPLAY_PASSED=false")
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
