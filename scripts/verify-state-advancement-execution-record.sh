#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
FROM_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
TO_STATE = "RELEASE_CANDIDATE_READY"

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def maybe_load(path):
    p = Path(path)
    return load(path) if p.exists() else None

record = maybe_load("CINEMATICUM_STATE_ADVANCEMENT_EXECUTION_RECORD.json")
law = maybe_load("CINEMATICUM_STATE_ADVANCEMENT_EXECUTION_RECORD_LAW.json")
case_record = maybe_load("CASES/CASE_001_THE_LAST_RENDER/STATE_ADVANCEMENT_EXECUTION_RECORD/STATE_ADVANCEMENT_EXECUTION_RECORD.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/STATE_ADVANCEMENT_EXECUTION_RECORD_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

objects = [obj for obj in (record, law, case_record, status) if obj is not None]

for obj in objects:
    if "case_id" in obj:
        assert obj["case_id"] == CASE_ID
    if "current_state" in obj:
        assert obj["current_state"] == FROM_STATE, obj["current_state"]
    if "requested_next_state" in obj:
        assert obj["requested_next_state"] == TO_STATE
    if "execution_object" in obj:
        assert obj["execution_object"] == "STATE_ADVANCEMENT_EXECUTION_RECORD"
    if "prior_decision_object" in obj:
        assert obj["prior_decision_object"] == "EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD"
    if "state_mutation_execution_authorized" in obj:
        assert obj["state_mutation_execution_authorized"] is True
    if "current_state_index_mutation_authorized" in obj:
        assert obj["current_state_index_mutation_authorized"] is True
    if "current_state_index_change_deferred_to_next_object" in obj:
        assert obj["current_state_index_change_deferred_to_next_object"] is True
    if "issued" in obj:
        assert obj["issued"] is False
    if "media_present" in obj:
        assert obj["media_present"] is False

assert index["active_case_states"][CASE_ID] == "RELEASE_CANDIDATE_READY", index["active_case_states"][CASE_ID]
assert index["active_current_state"] == "RELEASE_CANDIDATE_READY", index["active_current_state"]
assert case["current_state"] == "RELEASE_CANDIDATE_READY", case["current_state"]
assert case["release_candidate_ready"] is True
assert not case["issued"] is True, case["issued"]
assert not case["media_present"] is True, case["media_present"]

print("CINEMATICUM STATE ADVANCEMENT EXECUTION RECORD: PASS")
print(f"RECORD_CURRENT_STATE={FROM_STATE}")
print("ACTIVE_CURRENT_STATE=RELEASE_CANDIDATE_READY")
print("EXECUTION_SCOPE=POST_EXPLICIT_STATE_ADVANCEMENT_DECISION_EXECUTION_RECORD_ONLY")
print("EXECUTION_OBJECT=STATE_ADVANCEMENT_EXECUTION_RECORD")
print("STATE_MUTATION_EXECUTION_AUTHORIZED=true")
print("CURRENT_STATE_INDEX_MUTATION_AUTHORIZED=true")
print("CURRENT_STATE_INDEX_MUTATION_EXECUTED=true")
print("RELEASE_CANDIDATE_READY=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("RECORD_NEXT_REQUIRED_OBJECT=CURRENT_STATE_INDEX_ADVANCEMENT_RECORD")
print("ACTIVE_NEXT_REQUIRED_OBJECT=MOTION_PICTURE_ISSUANCE_ACT")
PY
