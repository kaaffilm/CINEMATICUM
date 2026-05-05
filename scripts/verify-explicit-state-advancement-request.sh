#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
REQUEST_OBJECT = "EXPLICIT_STATE_ADVANCEMENT_REQUEST"
REQUEST_ID = "REQ_001_EXPLICIT_STATE_ADVANCEMENT_REQUEST"
REQUESTED_NEXT_STATE = "RELEASE_CANDIDATE_READY"
PRIOR_GATE = "FUTURE_AUTHORITY_SATISFACTION_GATE"
NEXT_REQUIRED_OBJECT = "EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD"

PATHS = {
    "law": Path("CINEMATICUM_EXPLICIT_STATE_ADVANCEMENT_REQUEST_LAW.json"),
    "status": Path("CASES/CASE_001_THE_LAST_RENDER/EXPLICIT_STATE_ADVANCEMENT_REQUEST_STATUS.json"),
    "request": Path("CASES/CASE_001_THE_LAST_RENDER/EXPLICIT_STATE_ADVANCEMENT_REQUEST/EXPLICIT_STATE_ADVANCEMENT_REQUEST.json"),
    "prior_gate_status": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_AUTHORITY_SATISFACTION_GATE_STATUS.json"),
    "prior_gate": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_AUTHORITY_SATISFACTION_GATE/FUTURE_AUTHORITY_SATISFACTION_GATE.json"),
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
        "explicit_transition_record_required_before_advancement",
    ):
        if not bool_value(docs[prior], [field], default=False):
            raise SystemExit(f"{prior} required true field false/missing: {field}")

for label in ("law", "status", "request"):
    for expected in (CURRENT_STATE, REQUEST_OBJECT, REQUEST_ID, REQUESTED_NEXT_STATE, PRIOR_GATE, NEXT_REQUIRED_OBJECT):
        if not contains_value(docs[label], expected):
            raise SystemExit(f"{label} missing expected value: {expected}")

required_true = (
    "future_authority_satisfaction_gate_passed",
    "authority_object_stack_complete",
    "all_required_future_authority_objects_instantiated",
    "terminal_closure_authority_locked",
    "explicit_state_advancement_request_present",
    "request_is_not_decision",
    "request_does_not_advance_state",
    "request_does_not_mutate_current_state",
    "request_does_not_create_release_candidate",
    "request_does_not_issue_motion_picture",
    "request_does_not_admit_media",
    "advancement_decision_record_required_before_state_mutation",
    "current_state_unchanged",
)

for label in ("law", "status", "request"):
    for field in required_true:
        if not bool_value(docs[label], [field], default=False):
            raise SystemExit(f"{label} required true field false/missing: {field}")

for label in ("law", "status", "request"):
    for field in (
        "authority_satisfied",
        "may_advance_now",
        "release_candidate_ready",
        "issued",
        "media_present",
    ):
        if bool_value(docs[label], [field], default=False):
            raise SystemExit(f"{label} forbidden true value: {field}")

print("CINEMATICUM EXPLICIT STATE ADVANCEMENT REQUEST: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("REQUEST_SCOPE=POST_FUTURE_AUTHORITY_SATISFACTION_GATE_TRANSITION_REQUEST_ONLY")
print(f"REQUEST_OBJECT={REQUEST_OBJECT}")
print(f"REQUEST_ID={REQUEST_ID}")
print(f"REQUESTED_NEXT_STATE={REQUESTED_NEXT_STATE}")
print(f"REQUIRED_PRIOR_GATE={PRIOR_GATE}")
print("FUTURE_AUTHORITY_SATISFACTION_GATE_PASSED=true")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("ALL_REQUIRED_FUTURE_AUTHORITY_OBJECTS_INSTANTIATED=true")
print("TERMINAL_CLOSURE_AUTHORITY_LOCKED=true")
print("EXPLICIT_STATE_ADVANCEMENT_REQUEST_PRESENT=true")
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
