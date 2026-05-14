#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json
test -f CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE_LAW.json
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_INSTANTIATION_GATE_STATUS.json

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
ACTIVE_TARGET = 'RELEASE_CANDIDATE_READY'
CASE = 'CASE_001_THE_LAST_RENDER'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'
AUTHORITY_OBJECTS = ['CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/EDITORIAL_TIMELINE_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/COLOR_GRADE_LOCK_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/RELEASE_DELIVERY_ARTIFACTS_LOCK_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/ARCHIVIST_PROOF_CHAIN_LOCK_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/OUTSIDER_REPLAY_PASSAGE_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/TERMINAL_CLOSURE_AUTHORITY_OBJECT.json']
FALSE_KEYS = ['release_candidate_ready', 'release_candidate_artifacts_bound', 'issued', 'media_present', 'outsider_replay_passed', 'admissibility_verdict_present', 'terminal_closure_present', 'may_advance_now', 'issuance_unblocked']

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

gate = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_INSTANTIATION_GATE_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
required = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
template_kit = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert gate["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE_LAW"
assert status["status"] == "PASS"

for obj in (gate, law, status):
    assert obj["case_id"] == CASE
    assert obj["current_state"] == TARGET
    assert obj["authority_object_instantiation_gate_passed"] is True
    assert obj["authority_object_stack_complete"] is True
    assert obj["required_authority_objects_missing"] is False
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["instantiated_authority_object_paths"] == AUTHORITY_OBJECTS
    assert obj["schemas_do_not_satisfy_authority_objects"] is True
    assert obj["next_required_object"] == NEXT_OBJECT
    for key in FALSE_KEYS:
        assert obj[key] is False, key

for rel in AUTHORITY_OBJECTS:
    p = Path(rel)
    assert p.exists(), rel
    data = load(rel)
    assert data["case_id"] == CASE
    assert data["current_state"] == TARGET
    assert data.get("instantiated") is True
    assert data.get("accepted") is True
    for key in FALSE_KEYS:
        assert data.get(key) is False, f"{rel}:{key}"

assert index["active_case_states"][CASE] == ACTIVE_TARGET, index["active_case_states"][CASE]
assert case["current_state"] == ACTIVE_TARGET, case["current_state"]
assert required["current_state"] == TARGET
assert required["authority_object_stack_complete"] is True
assert template_kit["current_state"] == TARGET
assert registry["current_active_state"] in (ACTIVE_TARGET, "RELEASE_CANDIDATE_READY"), registry["current_active_state"]

print("CINEMATICUM AUTHORITY OBJECT INSTANTIATION GATE: PASS")
print(f"CURRENT_STATE={TARGET}")
print("AUTHORITY_OBJECT_INSTANTIATION_GATE_PASSED=true")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=8")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=8")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=0")
print("SCHEMAS_DO_NOT_SATISFY_AUTHORITY_OBJECTS=true")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
