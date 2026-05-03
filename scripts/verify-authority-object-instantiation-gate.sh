#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE_LAW.json
test -f CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json
test -f AUTHORITY_OBJECT_INSTANTIATION_GATE.md
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_INSTANTIATION_GATE_STATUS.json
test -d authority_objects
test -d templates/authority_objects
test -f authority_objects/README.md

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE_LAW.json")
gate = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_INSTANTIATION_GATE_STATUS.json")
template_kit = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
transition_gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")

current = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE_LAW"
assert law["law"]["templates_are_not_authority_objects"] is True
assert law["law"]["authority_object_requires_copy_outside_template_directory"] is True
assert law["law"]["authority_object_requires_template_only_false"] is True
assert law["law"]["authority_object_requires_accountable_actor"] is True
assert law["law"]["authority_object_requires_utc_timestamp"] is True
assert law["law"]["authority_object_requires_authority_basis"] is True
assert law["law"]["authority_object_requires_explicit_acceptance_or_rejection"] is True
assert law["law"]["authority_object_requires_hash_or_reference_material"] is True
assert law["law"]["authority_object_requires_verification_before_state_advance"] is True
assert law["law"]["instantiation_gate_may_not_itself_advance_state"] is True
assert law["law"]["instantiation_gate_may_not_issue_film"] is True
assert law["law"]["instantiation_gate_may_not_admit_media"] is True

assert gate["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE"
assert gate["current_state"] == current
assert gate["template_directory"] == "templates/authority_objects"
assert gate["instantiated_authority_directory"] == "authority_objects"
assert gate["instantiated_authority_objects_present"] is False
assert gate["authority_satisfied"] is False
assert gate["required_authority_objects_missing"] is True
assert gate["templates_do_not_satisfy_authority_objects"] is True
assert gate["may_advance_now"] is False
assert gate["release_candidate_ready"] is False
assert gate["issued"] is False
assert gate["media_present"] is False
assert gate["outsider_replay_passed"] is False
assert gate["terminal_closure_present"] is False
assert gate["currently_allowed_instantiations"] == []

assert status["current_state"] == current
assert status["instantiated_authority_objects_present"] is False
assert status["authority_satisfied"] is False
assert status["required_authority_objects_missing"] is True
assert status["templates_do_not_satisfy_authority_objects"] is True
assert status["may_advance_now"] is False
assert status["release_candidate_ready"] is False
assert status["issued"] is False
assert status["media_present"] is False
assert status["outsider_replay_passed"] is False
assert status["terminal_closure_present"] is False

assert template_kit["template_only"] is True
assert template_kit["authority_satisfied"] is False
assert template_kit["templates_do_not_satisfy_authority_objects"] is True

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
    vals = values_for_key(transition_gate, key)
    assert vals, key
    assert all(v is False for v in vals if isinstance(v, bool)), key

missing_claims = values_for_key(checklist, "required_authority_objects_missing")
assert missing_claims
assert any(v is True for v in missing_claims if isinstance(v, bool))

required_promotion_terms = {
    "copy template outside templates/authority_objects",
    "change template_only to false",
    "provide authority_actor",
    "provide authority_timestamp_utc",
    "provide authority_basis",
    "provide explicit_acceptance_or_rejection",
    "provide object_hashes_or_references",
    "provide signature_or_public_accountable_record",
    "pass dedicated authority-object verifier",
    "pass scripts/verify-all.sh"
}
assert required_promotion_terms.issubset(set(gate["promotion_requirements"]))

for future in gate["currently_forbidden_instantiations"]:
    assert not Path(future).exists(), future
    assert not Path("authority_objects", future).exists(), f"authority_objects/{future}"

actual_json = sorted(Path("authority_objects").glob("*.json"))
assert actual_json == [], [str(p) for p in actual_json]

template_json = sorted(Path("templates/authority_objects").glob("*_TEMPLATE.json"))
assert len(template_json) >= 8

for p in template_json:
    payload = load(str(p))
    assert payload["template_only"] is True
    assert payload["authority_satisfied"] is False
    assert payload["may_advance_state"] is False
    assert payload["issued"] is False
    assert payload["media_present"] is False

text = Path("AUTHORITY_OBJECT_INSTANTIATION_GATE.md").read_text(encoding="utf-8")
for needle in [
    "The instantiation gate is not an authority object",
    "instantiated_authority_objects_present=false",
    "authority_satisfied=false",
    "may_advance_now=false",
    "issued=false",
    "media_present=false"
]:
    assert needle in text, needle

print("CINEMATICUM AUTHORITY OBJECT INSTANTIATION GATE: PASS")
print("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("INSTANTIATED_AUTHORITY_OBJECTS_PRESENT=false")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
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
