#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_PRECEDENCE_LAW.json
test -f CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json
test -f AUTHORITY_PRECEDENCE.md
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_PRECEDENCE_STATUS.json

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_AUTHORITY_PRECEDENCE_LAW.json")
lattice = load("CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_PRECEDENCE_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
dossier = load("PUBLIC_INSPECTION_DOSSIER.json")
negative = load("PUBLIC_INSPECTION_NEGATIVE_PROOF.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert law["object_type"] == "CINEMATICUM_AUTHORITY_PRECEDENCE_LAW"
assert law["precedence_table_owner"] == "CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json"
assert law["current_state_owner"] == "CINEMATICUM_CURRENT_STATE_INDEX.json"
assert law["case_current_state_owner"] == "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"
assert "README_PROSE over ACTIVE_CURRENT_STATE" in law["forbidden_authority_inversions"]
assert "SCHEMA_OBJECT over LAW_OBJECT" in law["forbidden_authority_inversions"]

for key, expected in law["currently_false_claims"].items():
    assert expected is False, key

assert lattice["object_type"] == "CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE"
assert lattice["surface_type"] == "AUTHORITY_PRECEDENCE_LATTICE"
assert lattice["case_id"] == "CASE_001_THE_LAST_RENDER"
assert lattice["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

owners = {owner["path"] for owner in lattice["current_truth_owners"]}
assert owners == {
    "CINEMATICUM_CURRENT_STATE_INDEX.json",
    "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"
}

order = lattice["precedence_order"]
ranks = [entry["rank"] for entry in order]
assert ranks == sorted(ranks), ranks
assert order[0]["authority_class"] == "ACTIVE_CURRENT_STATE"
assert order[-1]["authority_class"] == "README_PROSE"
assert order[0]["may_override_current_state"] is True
for entry in order[1:]:
    assert entry["may_override_current_state"] is False, entry

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
    assert lattice["current_false_values"][key] is False, key

assert status["object_type"] == "CINEMATICUM_CASE_AUTHORITY_PRECEDENCE_STATUS"
assert status["surface_type"] == "LAYER_STATUS_RECORD"
assert status["current_truth_owner"] is False
assert status["active_current_state_owner"] == "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"
assert status["root_current_state_owner"] == "CINEMATICUM_CURRENT_STATE_INDEX.json"

for key in [
    "readme_prose_may_override_current_state",
    "schema_may_override_current_state",
    "registry_may_override_current_state",
    "status_seal_may_override_current_state",
    "public_inspection_may_override_current_state",
    "negative_proof_may_override_current_state",
    "release_candidate_ready",
    "issued",
    "media_present",
    "outsider_replay_passed",
    "admissibility_verdict_present",
    "terminal_closure_present"
]:
    assert status[key] is False, key

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == lattice["current_state"]
assert case["current_state"] == lattice["current_state"]
assert seal["current_state"] == lattice["current_state"]
assert dossier["current_state"] == lattice["current_state"]
assert negative["current_state"] == lattice["current_state"]
assert registry["current_active_state"] == lattice["current_state"]

text = Path("AUTHORITY_PRECEDENCE.md").read_text(encoding="utf-8")
for needle in [
    "The active current-state objects control",
    "CINEMATICUM_CURRENT_STATE_INDEX.json",
    "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json",
    "README prose",
    "release_candidate_ready=false",
    "issued=false",
    "media_present=false",
    "outsider_replay_passed=false",
    "does not issue a film",
    "does not admit media"
]:
    assert needle in text, needle

print("CINEMATICUM AUTHORITY PRECEDENCE LATTICE: PASS")
print("ACTIVE_CURRENT_STATE_OWNS=true")
print("README_MAY_OVERRIDE=false")
print("SCHEMA_MAY_OVERRIDE=false")
print("REGISTRY_MAY_OVERRIDE=false")
print("PUBLIC_SURFACES_MAY_OVERRIDE=false")
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
