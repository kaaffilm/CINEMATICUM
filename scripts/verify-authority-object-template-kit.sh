#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT_LAW.json
test -f CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json
test -f AUTHORITY_OBJECT_TEMPLATES.md
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_TEMPLATE_KIT_STATUS.json
test -d templates/authority_objects

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT_LAW.json")
kit = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_TEMPLATE_KIT_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")

current = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT_LAW"
assert law["law"]["templates_are_not_authority_objects"] is True
assert law["law"]["templates_may_not_satisfy_required_authority"] is True
assert law["law"]["templates_may_not_advance_current_state"] is True
assert law["law"]["templates_may_not_issue_film"] is True

assert kit["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT"
assert kit["current_state"] == current
assert kit["template_only"] is True
assert kit["authority_satisfied"] is False
assert kit["required_authority_objects_missing"] is True
assert kit["templates_do_not_satisfy_authority_objects"] is True
assert kit["may_advance_now"] is False
assert kit["release_candidate_ready"] is False
assert kit["issued"] is False
assert kit["media_present"] is False
assert kit["outsider_replay_passed"] is False

assert status["current_state"] == current
assert status["template_only"] is True
assert status["authority_satisfied"] is False
assert status["required_authority_objects_missing"] is True
assert status["templates_do_not_satisfy_authority_objects"] is True
assert status["may_advance_now"] is False
assert status["release_candidate_ready"] is False
assert status["issued"] is False
assert status["media_present"] is False

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == current
assert case["current_state"] == current

def values_for_key(obj, key):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append(v)
            out.extend(values_for_key(v, key))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(values_for_key(item, key))
    return out

for key in ["may_advance_now", "release_candidate_ready", "issued", "media_present"]:
    vals = values_for_key(gate, key)
    assert vals, key
    assert all(v is False for v in vals if isinstance(v, bool)), key

required_missing_claims = values_for_key(checklist, "required_authority_objects_missing")
assert required_missing_claims
assert any(v is True for v in required_missing_claims if isinstance(v, bool))

templates = kit["templates"]
assert len(templates) >= 8
seen = set()

for item in templates:
    path = Path(item["path"])
    assert path.exists(), str(path)
    assert str(path).startswith("templates/authority_objects/")
    payload = load(str(path))
    assert payload["object_type"].endswith("_TEMPLATE")
    assert payload["template_only"] is True
    assert payload["authority_satisfied"] is False
    assert payload["may_advance_state"] is False
    assert payload["release_candidate_ready"] is False
    assert payload["issued"] is False
    assert payload["media_present"] is False
    assert payload["future_authority_object"] == item["future_authority_object"]
    assert payload["must_be_copied_outside_template_directory_before_use"] is True
    seen.add(payload["future_authority_object"])

for forbidden_actual in seen:
    assert not Path(forbidden_actual).exists(), f"actual authority object unexpectedly exists: {forbidden_actual}"

text = Path("AUTHORITY_OBJECT_TEMPLATES.md").read_text(encoding="utf-8")
for needle in [
    "Templates are not authority objects",
    "templates_do_not_satisfy_authority_objects=true",
    "may_advance_now=false",
    "issued=false",
    "media_present=false"
]:
    assert needle in text, needle

print("CINEMATICUM AUTHORITY OBJECT TEMPLATE KIT: PASS")
print("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("TEMPLATE_ONLY=true")
print("AUTHORITY_SATISFIED=false")
print("TEMPLATES_DO_NOT_SATISFY_AUTHORITY_OBJECTS=true")
print("MAY_ADVANCE_NOW=false")
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
