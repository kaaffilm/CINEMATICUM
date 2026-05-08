#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CASE = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
OBJECT = "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST"
REQUEST_ID = "REQ_001_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST"
REQUESTED_NEXT_STATE = "RELEASE_CANDIDATE_READY"
PRIOR_OBJECT = "RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD"
NEXT_REQUIRED_OBJECT = "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_DECISION_RECORD"

paths = [
    Path("CINEMATICUM_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST_LAW.json"),
    Path("CINEMATICUM_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST.json"),
    Path(f"CASES/{CASE}/RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST/RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST.json"),
    Path(f"CASES/{CASE}/RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST_STATUS.json"),
]

prior_paths = [
    Path("CINEMATICUM_RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD_LAW.json"),
    Path("CINEMATICUM_RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD.json"),
    Path(f"CASES/{CASE}/RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD/RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD.json"),
    Path(f"CASES/{CASE}/RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD_STATUS.json"),
]

def load(path):
    if not path.exists():
        raise SystemExit(f"missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

docs = [load(p) for p in paths]
prior_docs = [load(p) for p in prior_paths]

merged = {}
for doc in [*prior_docs, *docs]:
    if isinstance(doc, dict):
        merged.update(doc)

required = {
    "current_state": CURRENT_STATE,
    "request_id": REQUEST_ID,
    "requested_next_state": REQUESTED_NEXT_STATE,
    "required_prior_object": PRIOR_OBJECT,
    "outsider_replay_execution_record_present": True,
    "outsider_replay_execution_completed": True,
    "outsider_replay_execution_result": "PASS",
    "outsider_replay_passage_record_present": True,
    "outsider_replay_passed": True,
    "admissibility_verdict_record_present": True,
    "admissibility_verdict_present": True,
    "admissibility_verdict_result": "ADMISSIBLE",
    "terminal_closure_record_present": True,
    "terminal_closure_present": True,
    "release_candidate_terminal_closure_record_present": True,
    "release_candidate_ready_state_advancement_request_present": True,
    "request_targets_current_state": True,
    "request_is_not_decision": True,
    "request_is_not_state_mutation": True,
    "request_does_not_advance_state": True,
    "request_does_not_mutate_current_state": True,
    "request_does_not_create_release_candidate": True,
    "request_does_not_issue_motion_picture": True,
    "request_does_not_admit_media": True,
    "advancement_decision_record_required_before_state_mutation": True,
    "authority_satisfied": False,
    "may_advance_now": False,
    "release_candidate_ready": False,
    "issued": False,
    "media_present": False,
    "current_state_unchanged": True,
    "next_required_object": NEXT_REQUIRED_OBJECT,
}

for key, expected in required.items():
    actual = merged.get(key)
    if actual != expected:
        raise SystemExit(f"{key}: expected {expected!r}, got {actual!r}")

object_types = {doc.get("object_type") for doc in docs}
if OBJECT not in object_types:
    raise SystemExit(f"missing object_type {OBJECT}")

print("CINEMATICUM RELEASE CANDIDATE READY STATE ADVANCEMENT REQUEST: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("REQUEST_SCOPE=POST_RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD_TRANSITION_REQUEST_ONLY")
print(f"REQUEST_OBJECT={OBJECT}")
print(f"REQUEST_ID={REQUEST_ID}")
print(f"REQUESTED_NEXT_STATE={REQUESTED_NEXT_STATE}")
print(f"REQUIRED_PRIOR_OBJECT={PRIOR_OBJECT}")
print("OUTSIDER_REPLAY_PASSED=true")
print("ADMISSIBILITY_VERDICT_PRESENT=true")
print("ADMISSIBILITY_VERDICT_RESULT=ADMISSIBLE")
print("TERMINAL_CLOSURE_PRESENT=true")
print("RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST_PRESENT=true")
print("REQUEST_IS_NOT_DECISION=true")
print("REQUEST_DOES_NOT_ADVANCE_STATE=true")
print("ADVANCEMENT_DECISION_RECORD_REQUIRED_BEFORE_STATE_MUTATION=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("CURRENT_STATE_UNCHANGED=true")
print(f"NEXT_REQUIRED_OBJECT={NEXT_REQUIRED_OBJECT}")
PY
