#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

TARGET = "RELEASE_CANDIDATE_READY"
CASE_ID = "CASE_001_THE_LAST_RENDER"

def load(path):
    return json.loads(Path(path).read_text())

index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
matrix = load("CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json")
graph = load("CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json")

assert index["active_case_states"][CASE_ID] == TARGET
assert case["current_state"] == TARGET

matrix_state = (
    matrix.get("current_active_state")
    or matrix.get("active_current_state")
    or matrix.get("current_state")
)
assert matrix_state == TARGET, matrix_state

graph_state = (
    graph.get("current_active_state")
    or graph.get("active_current_state")
    or graph.get("current_state")
)
assert graph_state == TARGET, graph_state

assert index.get("release_candidate_ready") is True
assert case.get("release_candidate_ready") is True
assert matrix.get("release_candidate_ready") is True
assert graph.get("release_candidate_ready") is True

nodes = graph.get("nodes", [])
active_nodes = [
    n for n in nodes
    if isinstance(n, dict) and (
        n.get("active") is True or n.get("status") == "active"
    )
]
assert len(active_nodes) == 1, active_nodes
assert active_nodes[0]["state"] == TARGET

for key in (
    "issued",
    "media_present",
    "outsider_replay_passed",
    "release_candidate_artifacts_bound",
):
    for obj in (index, case, matrix, graph):
        if key in obj:
            assert obj[key] is False, f"{key}={obj[key]}"

print("CINEMATICUM MASTER PROGRESSION: PASS")
print(f"CASE_001=THE_LAST_RENDER")
print(f"ACTIVE_CURRENT_STATE={TARGET}")
print("RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("REPLAY_PASSED=false")
print("MASTER_BATTERY=true")
PY
