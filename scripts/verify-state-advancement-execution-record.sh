#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

FROM_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
TO_STATE = "RELEASE_CANDIDATE_READY"
EXECUTION_OBJECT = "STATE_ADVANCEMENT_EXECUTION_RECORD"
EXECUTION_ID = "EXEC_001_STATE_ADVANCEMENT_TO_RELEASE_CANDIDATE_READY"
DECISION_OBJECT = "EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD"
DECISION_ID = "DEC_001_EXPLICIT_STATE_ADVANCEMENT"
REQUEST_OBJECT = "EXPLICIT_STATE_ADVANCEMENT_REQUEST"
REQUEST_ID = "REQ_001_EXPLICIT_STATE_ADVANCEMENT_REQUEST"
PRIOR_GATE = "FUTURE_AUTHORITY_SATISFACTION_GATE"
NEXT_REQUIRED_OBJECT = "CURRENT_STATE_INDEX_ADVANCEMENT_RECORD"

PATHS = {
    "law": Path("CINEMATICUM_STATE_ADVANCEMENT_EXECUTION_RECORD_LAW.json"),
    "status": Path("CASES/CASE_001_THE_LAST_RENDER/STATE_ADVANCEMENT_EXECUTION_RECORD_STATUS.json"),
    "record": Path("CASES/CASE_001_THE_LAST_RENDER/STATE_ADVANCEMENT_EXECUTION_RECORD/STATE_ADVANCEMENT_EXECUTION_RECORD.json"),
    "decision": Path("CASES/CASE_001_THE_LAST_RENDER/EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD/EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD.json"),
    "decision_status": Path("CASES/CASE_001_THE_LAST_RENDER/EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD_STATUS.json"),
    "request": Path("CASES/CASE_001_THE_LAST_RENDER/EXPLICIT_STATE_ADVANCEMENT_REQUEST/EXPLICIT_STATE_ADVANCEMENT_REQUEST.json"),
    "prior_gate": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_AUTHORITY_SATISFACTION_GATE/FUTURE_AUTHORITY_SATISFACTION_GATE.json"),
    "index": Path("CINEMATICUM_CURRENT_STATE_INDEX.json"),
    "case": Path("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
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

for label in ("decision", "decision_status"):
    for field in (
        "future_authority_satisfaction_gate_passed",
        "explicit_state_advancement_request_present",
        "decision_accepts_request",
        "decision_authorizes_state_mutation",
        "authority_satisfied_for_transition",
        "state_mutation_record_required_before_current_state_index_change",
        "current_state_unchanged"
    ):
        if not bool_value(docs[label], [field], default=False):
            raise SystemExit(f"{label} required true field false/missing: {field}")

for label in ("request", "prior_gate"):
    if not contains_value(docs[label], FROM_STATE) and label == "request":
        raise SystemExit(f"{label} missing from-state: {FROM_STATE}")

index = docs["index"]
case = docs["case"]

if index["active_case_states"]["CASE_001_THE_LAST_RENDER"] != FROM_STATE:
    raise SystemExit("current state index mutated before execution-record verification")
if index["release_candidate_ready_cases"] != []:
    raise SystemExit("release candidate readiness was asserted before index advancement record")
if index["issued_films"] != [] or index["media_admitted_cases"] != []:
    raise SystemExit("issuance/media was asserted before release admissibility")

if case["current_state"] != FROM_STATE:
    raise SystemExit("case current state mutated before index advancement record")
if case["release_candidate_ready"] is not False:
    raise SystemExit("case release_candidate_ready mutated before index advancement record")
if case["issued"] is not False or case["media_present"] is not False:
    raise SystemExit("case issuance/media mutated before index advancement record")

for label in ("law", "status", "record"):
    for expected in (
        FROM_STATE,
        TO_STATE,
        EXECUTION_OBJECT,
        EXECUTION_ID,
        DECISION_OBJECT,
        DECISION_ID,
        REQUEST_OBJECT,
        REQUEST_ID,
        PRIOR_GATE,
        NEXT_REQUIRED_OBJECT
    ):
        if not contains_value(docs[label], expected):
            raise SystemExit(f"{label} missing expected value: {expected}")

required_true = (
    "future_authority_satisfaction_gate_passed",
    "explicit_state_advancement_request_present",
    "explicit_state_advancement_decision_record_present",
    "decision_accepts_request",
    "decision_authorizes_state_mutation",
    "authority_satisfied_for_transition",
    "execution_record_present",
    "execution_scope_post_explicit_decision_only",
    "execution_applies_decision_record",
    "state_mutation_execution_authorized",
    "execution_record_required_before_current_state_index_change_satisfied",
    "current_state_index_mutation_authorized",
    "current_state_index_change_deferred_to_next_object",
    "current_state_index_still_points_to_from_state",
    "current_state_unchanged_until_index_advancement_record",
    "next_state_locked",
    "execution_does_not_issue_motion_picture",
    "execution_does_not_admit_media",
    "execution_does_not_create_media_payload"
)

required_false = (
    "authority_satisfied",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present"
)

for label in ("law", "status", "record"):
    for field in required_true:
        if not bool_value(docs[label], [field], default=False):
            raise SystemExit(f"{label} required true field false/missing: {field}")
    for field in required_false:
        if bool_value(docs[label], [field], default=False):
            raise SystemExit(f"{label} forbidden true field: {field}")

print("CINEMATICUM STATE ADVANCEMENT EXECUTION RECORD: PASS")
print(f"CURRENT_STATE={FROM_STATE}")
print("EXECUTION_SCOPE=POST_EXPLICIT_STATE_ADVANCEMENT_DECISION_EXECUTION_RECORD_ONLY")
print(f"EXECUTION_OBJECT={EXECUTION_OBJECT}")
print(f"EXECUTION_RECORD_ID={EXECUTION_ID}")
print(f"PRIOR_DECISION_OBJECT={DECISION_OBJECT}")
print(f"PRIOR_DECISION_ID={DECISION_ID}")
print(f"REQUESTED_NEXT_STATE={TO_STATE}")
print(f"REQUIRED_PRIOR_GATE={PRIOR_GATE}")
print("FUTURE_AUTHORITY_SATISFACTION_GATE_PASSED=true")
print("EXPLICIT_STATE_ADVANCEMENT_REQUEST_PRESENT=true")
print("EXPLICIT_STATE_ADVANCEMENT_DECISION_RECORD_PRESENT=true")
print("DECISION_AUTHORIZES_STATE_MUTATION=true")
print("AUTHORITY_SATISFIED_FOR_TRANSITION=true")
print("STATE_MUTATION_EXECUTION_AUTHORIZED=true")
print("CURRENT_STATE_INDEX_MUTATION_AUTHORIZED=true")
print("CURRENT_STATE_INDEX_CHANGE_DEFERRED_TO_NEXT_OBJECT=true")
print("CURRENT_STATE_INDEX_STILL_POINTS_TO_FROM_STATE=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print(f"NEXT_REQUIRED_OBJECT={NEXT_REQUIRED_OBJECT}")
PY
