#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
DECISION_OBJECT = "EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD"
DECISION_ID = "DEC_001_EXPLICIT_STATE_ADVANCEMENT"
REQUEST_OBJECT = "EXPLICIT_STATE_ADVANCEMENT_REQUEST"
REQUEST_ID = "REQ_001_EXPLICIT_STATE_ADVANCEMENT_REQUEST"
REQUESTED_NEXT_STATE = "RELEASE_CANDIDATE_READY"
PRIOR_GATE = "FUTURE_AUTHORITY_SATISFACTION_GATE"
NEXT_REQUIRED_OBJECT = "STATE_ADVANCEMENT_EXECUTION_RECORD"

PATHS = {
    "law": Path("CINEMATICUM_EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD_LAW.json"),
    "status": Path("CASES/CASE_001_THE_LAST_RENDER/EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD_STATUS.json"),
    "decision": Path("CASES/CASE_001_THE_LAST_RENDER/EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD/EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD.json"),
    "request": Path("CASES/CASE_001_THE_LAST_RENDER/EXPLICIT_STATE_ADVANCEMENT_REQUEST/EXPLICIT_STATE_ADVANCEMENT_REQUEST.json"),
    "request_status": Path("CASES/CASE_001_THE_LAST_RENDER/EXPLICIT_STATE_ADVANCEMENT_REQUEST_STATUS.json"),
    "prior_gate_status": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_AUTHORITY_SATISFACTION_GATE_STATUS.json"),
    "prior_gate": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_AUTHORITY_SATISFACTION_GATE/FUTURE_AUTHORITY_SATISFACTION_GATE.json")
}

def load(path):
    if not path.exists():
        raise SystemExit(f"missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def walk_items(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield str(k), v
            yield from walk_items(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_items(v)

def walk_values(node):
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from walk_values(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_values(v)

def norm(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)

def contains_value(node, expected):
    return any(norm(v) == norm(expected) for v in walk_values(node))

def find_key_value(node, names):
    wanted = {n.lower() for n in names}
    for key, value in walk_items(node):
        if key.lower() in wanted:
            return value
    raise KeyError(",".join(names))

def bool_value(node, names, default=None):
    try:
        value = find_key_value(node, names)
    except KeyError:
        if default is None:
            raise
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "yes", "1"}:
            return True
        if v in {"false", "no", "0"}:
            return False
    if isinstance(value, int):
        return bool(value)
    raise SystemExit(f"non-boolean value for {list(names)}: {value!r}")

docs = {name: load(path) for name, path in PATHS.items()}

for prior in ("prior_gate_status", "prior_gate"):
    for field in (
        "future_authority_satisfaction_gate_passed",
        "authority_object_stack_complete",
        "all_required_future_authority_objects_instantiated",
        "terminal_closure_authority_locked",
        "explicit_transition_record_required_before_advancement"
    ):
        if not bool_value(docs[prior], [field], default=False):
            raise SystemExit(f"{prior} required true field false/missing: {field}")

for req in ("request", "request_status"):
    for field in (
        "explicit_state_advancement_request_present",
        "request_is_not_decision",
        "request_does_not_advance_state",
        "advancement_decision_record_required_before_state_mutation",
        "current_state_unchanged"
    ):
        if not bool_value(docs[req], [field], default=False):
            raise SystemExit(f"{req} required request precondition false/missing: {field}")

for label in ("law", "status", "decision"):
    for expected in (
        CURRENT_STATE,
        DECISION_OBJECT,
        DECISION_ID,
        REQUEST_OBJECT,
        REQUEST_ID,
        REQUESTED_NEXT_STATE,
        PRIOR_GATE,
        NEXT_REQUIRED_OBJECT
    ):
        if not contains_value(docs[label], expected):
            raise SystemExit(f"{label} missing expected value: {expected}")

required_true = (
    "future_authority_satisfaction_gate_passed",
    "authority_object_stack_complete",
    "all_required_future_authority_objects_instantiated",
    "terminal_closure_authority_locked",
    "explicit_state_advancement_request_present",
    "decision_record_present",
    "decision_is_not_request",
    "decision_accepts_request",
    "request_schema_valid",
    "request_targets_current_state",
    "decision_is_state_advancement_authority",
    "decision_authorizes_state_mutation",
    "authority_satisfied_for_transition",
    "may_advance_after_state_mutation_record",
    "state_mutation_record_required_before_current_state_index_change",
    "decision_does_not_mutate_current_state",
    "decision_does_not_create_release_candidate_now",
    "decision_does_not_issue_motion_picture",
    "decision_does_not_admit_media",
    "decision_does_not_create_release_media",
    "current_state_unchanged"
)

for label in ("law", "status", "decision"):
    for field in required_true:
        if not bool_value(docs[label], [field], default=False):
            raise SystemExit(f"{label} required true field false/missing: {field}")

for label in ("law", "status", "decision"):
    for field in (
        "authority_satisfied",
        "may_advance_now",
        "release_candidate_ready",
        "issued",
        "media_present"
    ):
        if bool_value(docs[label], [field], default=False):
            raise SystemExit(f"{label} forbidden true value: {field}")

print("CINEMATICUM EXPLICIT STATE ADVANCEMENT DECISION RECORD: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("DECISION_SCOPE=POST_EXPLICIT_STATE_ADVANCEMENT_REQUEST_DECISION_ONLY")
print(f"DECISION_OBJECT={DECISION_OBJECT}")
print(f"DECISION_ID={DECISION_ID}")
print(f"REQUEST_OBJECT={REQUEST_OBJECT}")
print(f"REQUEST_ID={REQUEST_ID}")
print(f"REQUESTED_NEXT_STATE={REQUESTED_NEXT_STATE}")
print(f"REQUIRED_PRIOR_GATE={PRIOR_GATE}")
print("FUTURE_AUTHORITY_SATISFACTION_GATE_PASSED=true")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("ALL_REQUIRED_FUTURE_AUTHORITY_OBJECTS_INSTANTIATED=true")
print("TERMINAL_CLOSURE_AUTHORITY_LOCKED=true")
print("EXPLICIT_STATE_ADVANCEMENT_REQUEST_PRESENT=true")
print("DECISION_ACCEPTS_REQUEST=true")
print("DECISION_AUTHORIZES_STATE_MUTATION=true")
print("AUTHORITY_SATISFIED_FOR_TRANSITION=true")
print("STATE_MUTATION_RECORD_REQUIRED_BEFORE_CURRENT_STATE_INDEX_CHANGE=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("CURRENT_STATE_UNCHANGED=true")
print(f"NEXT_REQUIRED_OBJECT={NEXT_REQUIRED_OBJECT}")
PY
