#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json
test -f CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT_LAW.json
test -f CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_TEMPLATE_KIT_STATUS.json

python3 - <<'PY2'
import json
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
ACTIVE_TARGET = 'ISSUED_ADMISSIBLE_MOTION_PICTURE'
CASE = 'CASE_001_THE_LAST_RENDER'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'
TEMPLATES = ['templates/authority_objects/DIRECTOR_ACCEPTANCE_OBJECT_TEMPLATE.json', 'templates/authority_objects/FINAL_CUT_TIMELINE_LOCK_TEMPLATE.json', 'templates/authority_objects/SOUND_MIX_LOCK_TEMPLATE.json', 'templates/authority_objects/COLOR_GRADE_LOCK_TEMPLATE.json', 'templates/authority_objects/MEDIA_HASH_MANIFEST_TEMPLATE.json', 'templates/authority_objects/REPLAY_EXECUTION_REPORT_TEMPLATE.json', 'templates/authority_objects/ADMISSIBILITY_VERDICT_TEMPLATE.json', 'templates/authority_objects/TERMINAL_CLOSURE_CANDIDATE_TEMPLATE.json']

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

kit = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json")
law = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_TEMPLATE_KIT_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
required = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert kit["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT"
assert law["object_type"] == "CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT_LAW"
assert status["status"] == "PASS"

for p in TEMPLATES:
    assert Path(p).exists(), p

for obj in (kit, law, status):
    assert obj["case_id"] == CASE
    assert obj["current_state"] == TARGET
    assert obj["required_authority_object_template_count"] == 8
    assert obj["template_paths"] == TEMPLATES
    assert obj["template_only"] is True
    assert obj["templates_do_not_satisfy_authority_objects"] is True
    assert obj["authority_object_stack_complete"] is True
    assert obj["required_authority_objects_missing"] is False
    assert obj["accepted_authority_object_count"] == 8
    assert obj["instantiated_authority_object_count"] == 8
    assert obj["unfilled_authority_object_slot_count"] == 0
    assert obj["release_candidate_ready"] is False
    assert obj["release_candidate_artifacts_bound"] is False
    assert obj["issued"] is False
    assert obj["media_present"] is False
    assert obj["outsider_replay_passed"] is False
    assert obj["admissibility_verdict_present"] is False
    assert obj["terminal_closure_present"] is False
    assert obj["may_advance_now"] is False
    assert obj["issuance_unblocked"] is False
    assert obj["next_required_object"] == NEXT_OBJECT

assert index["active_case_states"][CASE] == ACTIVE_TARGET, index["active_case_states"][CASE]
assert case["current_state"] == ACTIVE_TARGET, case["current_state"]
assert required["current_state"] == TARGET
assert registry["current_active_state"] in (ACTIVE_TARGET, "RELEASE_CANDIDATE_READY"), registry["current_active_state"]

print("CINEMATICUM AUTHORITY OBJECT TEMPLATE KIT: PASS")
print(f"CURRENT_STATE={TARGET}")
print("REQUIRED_AUTHORITY_OBJECT_TEMPLATE_COUNT=8")
print("TEMPLATE_ONLY=true")
print("TEMPLATES_DO_NOT_SATISFY_AUTHORITY_OBJECTS=true")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("REQUIRED_AUTHORITY_OBJECTS_MISSING=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY2
