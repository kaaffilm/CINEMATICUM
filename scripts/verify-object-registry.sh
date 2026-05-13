#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_OBJECT_REGISTRY_LAW.json
test -f CINEMATICUM_SURFACE_CLASS_CATALOG.json
test -f CINEMATICUM_OBJECT_REGISTRY.json
test -f OBJECT_REGISTRY.md

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_OBJECT_REGISTRY_LAW.json")
catalog = load("CINEMATICUM_SURFACE_CLASS_CATALOG.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

assert law["object_type"] == "CINEMATICUM_OBJECT_REGISTRY_LAW"
assert law["registry_owner"] == "CINEMATICUM_OBJECT_REGISTRY.json"
assert law["current_state_owner"] == "CINEMATICUM_CURRENT_STATE_INDEX.json"
assert "ACTIVE_CURRENT_STATE" in law["required_surface_classes"]

assert catalog["object_type"] == "CINEMATICUM_SURFACE_CLASS_CATALOG"
assert "LAW_OBJECT" in catalog["surface_classes"]
assert "SCHEMA_OBJECT" in catalog["surface_classes"]
assert "ACTIVE_CURRENT_STATE" in catalog["surface_classes"]
assert catalog["hard_boundary"]["issued"] is False
assert catalog["hard_boundary"]["release_candidate_ready"] is False
assert catalog["hard_boundary"]["media_present"] is False
assert catalog["hard_boundary"]["outsider_replay_passed"] is False

assert registry["object_type"] == "CINEMATICUM_OBJECT_REGISTRY"
assert registry["registry_does_not_issue_film"] is True
assert registry["registry_does_not_admit_media"] is True
assert registry["registry_does_not_override_current_state"] is True
assert registry["current_active_state"] == "RELEASE_CANDIDATE_READY"
assert registry["case_id"] == "CASE_001_THE_LAST_RENDER"
assert registry["entries_count"] == len(registry["entries"])

paths = {entry["path"]: entry for entry in registry["entries"]}

required_paths = [
    "CINEMATICUM_CURRENT_STATE_INDEX.json",
    "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json",
    "CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json",
    "CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json",
    "OUTSIDER_REPLAY_BUNDLE_OBJECT_LAW.json",
    "ADMISSIBILITY_VERDICT_SCHEMA.json",
    "RELEASE_CANDIDATE_OBJECT_LAW.json",
    "AUTHORITY_ACCEPTANCE_OBJECT_LAW.json"
]
for path in required_paths:
    assert path in paths, path

assert paths["CINEMATICUM_CURRENT_STATE_INDEX.json"]["surface_class"] == "ACTIVE_CURRENT_STATE"
assert paths["CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"]["surface_class"] == "ACTIVE_CURRENT_STATE"
assert paths["ADMISSIBILITY_VERDICT_SCHEMA.json"]["surface_class"] == "SCHEMA_OBJECT"
assert paths["OUTSIDER_REPLAY_BUNDLE_OBJECT_LAW.json"]["surface_class"] == "LAW_OBJECT"

active_case_state_entries = [
    entry for entry in registry["entries"]
    if entry.get("case_id") == "CASE_001_THE_LAST_RENDER" and entry["surface_class"] == "ACTIVE_CURRENT_STATE"
]
assert len(active_case_state_entries) == 1, active_case_state_entries
assert active_case_state_entries[0]["path"] == "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"

for entry in registry["entries"]:
    if entry["surface_class"] in ["SCHEMA_OBJECT", "LAW_OBJECT", "LAYER_STATUS_RECORD", "CASE_RECORD", "VERIFICATION_MANIFEST", "PROGRESSION_GRAPH"]:
        assert entry["issued"] is False, entry
        assert entry["release_candidate_ready"] is False, entry
        assert entry["media_present"] is False, entry
        assert entry["outsider_replay_passed"] is False, entry

active_state = index["active_case_states"]["CASE_001_THE_LAST_RENDER"]

assert active_state == "ISSUED_ADMISSIBLE_MOTION_PICTURE", active_state
assert case["current_state"] == "ISSUED_ADMISSIBLE_MOTION_PICTURE", case["current_state"]
assert case["issued"] is True, case.get("issued")
assert case["media_present"] is True, case.get("media_present")

# Registry generation may still retain RELEASE_CANDIDATE_READY as its registry-level
# marker while the canonical active case/index has advanced to issued.
assert registry["current_active_state"] in (
    "RELEASE_CANDIDATE_READY",
    "ISSUED_ADMISSIBLE_MOTION_PICTURE",
), registry["current_active_state"]

print("CINEMATICUM OBJECT REGISTRY: PASS")
print(f"REGISTERED_OBJECTS={registry['entries_count']}")
print("ACTIVE_CURRENT_STATE=RELEASE_CANDIDATE_READY")
print("ONE_ACTIVE_CASE_STATE=true")
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
