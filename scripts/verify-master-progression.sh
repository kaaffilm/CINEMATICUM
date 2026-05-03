#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json
test -f CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json
test -f CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json
test -f MASTER_PROGRESSION.md

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

matrix = load("CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json")
manifest = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json")
graph = load("CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

assert matrix["object_type"] == "CINEMATICUM_GOVERNED_PROGRESSION_MATRIX"
assert matrix["case_id"] == "CASE_001_THE_LAST_RENDER"
assert matrix["current_active_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert "RELEASE_CANDIDATE_READY" in matrix["states_not_reached"]
assert "ISSUED_ADMISSIBLE_MOTION_PICTURE" in matrix["states_not_reached"]

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
    assert matrix["currently_false_claims"][key] is False, key

assert manifest["object_type"] == "CINEMATICUM_MASTER_VERIFICATION_MANIFEST"
for script in manifest["required_scripts"]:
    assert Path(script).is_file(), script
for test_file in manifest["required_unittests"]:
    assert Path(test_file).is_file(), test_file

assert graph["object_type"] == "CINEMATICUM_CASE_PROGRESSION_GRAPH"
assert graph["case_id"] == "CASE_001_THE_LAST_RENDER"
assert graph["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

active_nodes = [node for node in graph["nodes"] if node["status"] == "active"]
assert len(active_nodes) == 1, active_nodes
assert active_nodes[0]["state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

states = {node["state"]: node["status"] for node in graph["nodes"]}
assert states["RELEASE_CANDIDATE_READY"] == "not_reached"
assert states["ISSUED_ADMISSIBLE_MOTION_PICTURE"] == "not_reached"

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == matrix["current_active_state"]
assert case["current_state"] == matrix["current_active_state"]
assert case["release_candidate_ready"] is False
assert case["issued"] is False
assert case["media_present"] is False
assert case["outsider_replay_passed"] is False

for path in Path(".").rglob("*.json"):
    if ".git" in path.parts:
        continue
    json.loads(path.read_text(encoding="utf-8"))

active = []
for path in Path("CASES").rglob("*.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("case_id") == "CASE_001_THE_LAST_RENDER" and data.get("surface_type") == "ACTIVE_CURRENT_STATE":
        active.append(str(path))
assert active == ["CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"], active

print("CINEMATICUM MASTER PROGRESSION: PASS")
print("CASE_001=THE_LAST_RENDER")
print("ACTIVE_CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("REPLAY_PASSED=false")
print("MASTER_BATTERY=true")
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
