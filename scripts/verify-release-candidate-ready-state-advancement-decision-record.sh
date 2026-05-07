#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PYVERIFY'
import json
from pathlib import Path
import sys

ROOT = Path.cwd()
CASE = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"

REQUEST_OBJECT = "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST"
REQUEST_ID = "REQ_001_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST"
DECISION_OBJECT = "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_DECISION_RECORD"
DECISION_ID = "DEC_001_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT"
REQUESTED_NEXT_STATE = "RELEASE_CANDIDATE_READY"
REQUIRED_PRIOR_OBJECT = "RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD"
NEXT_REQUIRED_OBJECT = "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_EXECUTION_RECORD"

decision_path = ROOT / "CINEMATICUM_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_DECISION_RECORD.json"
law_path = ROOT / "CINEMATICUM_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_DECISION_RECORD_LAW.json"
case_path = ROOT / "CASES" / CASE / DECISION_OBJECT / f"{DECISION_ID}.json"
status_path = ROOT / "CASES" / CASE / f"{DECISION_OBJECT}_STATUS.json"
request_path = ROOT / "CINEMATICUM_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST.json"

required_paths = [decision_path, law_path, case_path, status_path, request_path]
missing = [str(p) for p in required_paths if not p.exists()]
if missing:
    print("CINEMATICUM RELEASE CANDIDATE READY STATE ADVANCEMENT DECISION RECORD: FAIL")
    print("MISSING=" + ",".join(missing))
    sys.exit(1)

decision = json.loads(decision_path.read_text())
status = json.loads(status_path.read_text())

checks = {
    "decision_object": decision.get("decision_object") == DECISION_OBJECT,
    "decision_id": decision.get("decision_id") == DECISION_ID,
    "request_object": decision.get("request_object") == REQUEST_OBJECT,
    "request_id": decision.get("request_id") == REQUEST_ID,
    "requested_next_state": decision.get("requested_next_state") == REQUESTED_NEXT_STATE,
    "required_prior_object": decision.get("required_prior_object") == REQUIRED_PRIOR_OBJECT,
    "outsider_replay_passed": decision.get("outsider_replay_passed") is True,
    "admissibility_verdict_present": decision.get("admissibility_verdict_present") is True,
    "admissibility_verdict_result": decision.get("admissibility_verdict_result") == "ADMISSIBLE",
    "terminal_closure_present": decision.get("terminal_closure_present") is True,
    "release_candidate_ready_state_advancement_request_present": decision.get("release_candidate_ready_state_advancement_request_present") is True,
    "decision_accepts_request": decision.get("decision_accepts_request") is True,
    "decision_authorizes_state_mutation": decision.get("decision_authorizes_state_mutation") is True,
    "authority_satisfied_for_transition": decision.get("authority_satisfied_for_transition") is True,
    "state_mutation_record_required_before_current_state_index_change": decision.get("state_mutation_record_required_before_current_state_index_change") is True,
    "authority_satisfied_remains_false": decision.get("authority_satisfied") is False,
    "may_advance_now_remains_false": decision.get("may_advance_now") is False,
    "release_candidate_ready_remains_false": decision.get("release_candidate_ready") is False,
    "issued_remains_false": decision.get("issued") is False,
    "media_present_remains_false": decision.get("media_present") is False,
    "current_state_unchanged": decision.get("current_state_unchanged") is True,
    "next_required_object": decision.get("next_required_object") == NEXT_REQUIRED_OBJECT,
    "status_pass": status.get("verification_result") == "PASS",
}

failed = [k for k, v in checks.items() if not v]
if failed:
    print("CINEMATICUM RELEASE CANDIDATE READY STATE ADVANCEMENT DECISION RECORD: FAIL")
    print("FAILED_CHECKS=" + ",".join(failed))
    sys.exit(1)

lines = [
    "CINEMATICUM RELEASE CANDIDATE READY STATE ADVANCEMENT DECISION RECORD: PASS",
    f"CURRENT_STATE={CURRENT_STATE}",
    "DECISION_SCOPE=POST_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST_DECISION_ONLY",
    f"DECISION_OBJECT={DECISION_OBJECT}",
    f"DECISION_ID={DECISION_ID}",
    f"REQUEST_OBJECT={REQUEST_OBJECT}",
    f"REQUEST_ID={REQUEST_ID}",
    f"REQUESTED_NEXT_STATE={REQUESTED_NEXT_STATE}",
    f"REQUIRED_PRIOR_OBJECT={REQUIRED_PRIOR_OBJECT}",
    "OUTSIDER_REPLAY_PASSED=true",
    "ADMISSIBILITY_VERDICT_PRESENT=true",
    "ADMISSIBILITY_VERDICT_RESULT=ADMISSIBLE",
    "TERMINAL_CLOSURE_PRESENT=true",
    "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST_PRESENT=true",
    "DECISION_ACCEPTS_REQUEST=true",
    "DECISION_AUTHORIZES_STATE_MUTATION=true",
    "AUTHORITY_SATISFIED_FOR_TRANSITION=true",
    "STATE_MUTATION_RECORD_REQUIRED_BEFORE_CURRENT_STATE_INDEX_CHANGE=true",
    "AUTHORITY_SATISFIED=false",
    "MAY_ADVANCE_NOW=false",
    "RELEASE_CANDIDATE_READY=false",
    "ISSUED=false",
    "MEDIA_PRESENT=false",
    "CURRENT_STATE_UNCHANGED=true",
    f"NEXT_REQUIRED_OBJECT={NEXT_REQUIRED_OBJECT}",
]
print("\n".join(lines))
PYVERIFY
