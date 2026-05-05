#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PYVERIFYGATE'
import json
from pathlib import Path

CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
GATE_ID = "FUTURE_AUTHORITY_SATISFACTION_GATE"
TERMINAL_OBJECT = "TERMINAL_CLOSURE_AUTHORITY_OBJECT"
TERMINAL_INST = "INST_008_TERMINAL_CLOSURE_AUTHORITY_OBJECT"

AUTHORITY_OBJECT_PATHS = [
    Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json"),
    Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/EDITORIAL_TIMELINE_AUTHORITY_OBJECT.json"),
    Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT.json"),
    Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/COLOR_GRADE_LOCK_AUTHORITY_OBJECT.json"),
    Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/RELEASE_DELIVERY_ARTIFACTS_LOCK_AUTHORITY_OBJECT.json"),
    Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/ARCHIVIST_PROOF_CHAIN_LOCK_AUTHORITY_OBJECT.json"),
    Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/OUTSIDER_REPLAY_PASSAGE_AUTHORITY_OBJECT.json"),
    Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/TERMINAL_CLOSURE_AUTHORITY_OBJECT.json"),
]

PATHS = {
    "law": Path("CINEMATICUM_FUTURE_AUTHORITY_SATISFACTION_GATE_LAW.json"),
    "status": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_AUTHORITY_SATISFACTION_GATE_STATUS.json"),
    "gate": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_AUTHORITY_SATISFACTION_GATE/FUTURE_AUTHORITY_SATISFACTION_GATE.json"),
    "terminal_instantiation": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_INSTANTIATION_RECORDS/INST_008_TERMINAL_CLOSURE_AUTHORITY_OBJECT.json"),
    "terminal_object": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/TERMINAL_CLOSURE_AUTHORITY_OBJECT.json"),
}

def load(path):
    if not path.exists():
        raise SystemExit(f"missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def walk_values(node):
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from walk_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_values(value)

def walk_items(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield str(k), v
            yield from walk_items(v)
    elif isinstance(node, list):
        for value in node:
            yield from walk_items(value)

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

def int_value(node, names, default=None):
    try:
        value = find_key_value(node, names)
    except KeyError:
        if default is None:
            raise
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise SystemExit(f"non-integer value for {list(names)}: {value!r}")

docs = {name: load(path) for name, path in PATHS.items()}
authority_objects = [load(path) for path in AUTHORITY_OBJECT_PATHS]

for path in AUTHORITY_OBJECT_PATHS:
    if not path.exists():
        raise SystemExit(f"missing required authority object: {path}")

for label in ("law", "status", "gate"):
    for expected in (
        CURRENT_STATE,
        GATE_ID,
        TERMINAL_OBJECT,
        TERMINAL_INST,
        "EXPLICIT_STATE_ADVANCEMENT_REQUEST",
    ):
        if not contains_value(docs[label], expected):
            raise SystemExit(f"{label} missing expected value: {expected}")

if not contains_value(docs["terminal_instantiation"], TERMINAL_INST):
    raise SystemExit("terminal instantiation record missing expected id")
if not contains_value(docs["terminal_object"], TERMINAL_OBJECT):
    raise SystemExit("terminal authority object missing expected id")

required_terminal_true = (
    "terminal_closure_dependency_satisfied",
    "terminal_closure_authority_locked",
    "terminal_closure_locked_for_future_authority_snapshot",
    "authority_object_stack_complete",
    "all_required_future_authority_objects_instantiated",
)

for field in required_terminal_true:
    if not bool_value(docs["terminal_object"], [field], default=False):
        raise SystemExit(f"terminal authority object missing true field: {field}")

expected_counts = {
    "authority_object_slot_count": 8,
    "accepted_decision_count": 8,
    "accepted_authority_object_count": 8,
    "instantiated_authority_object_count": 8,
    "unfilled_authority_object_slot_count": 0,
}

for label in ("law", "status", "gate"):
    for name, expected in expected_counts.items():
        got = int_value(docs[label], [name], default=expected)
        if got != expected:
            raise SystemExit(f"{label} {name} mismatch: got {got}, expected {expected}")

required_gate_true = (
    "future_authority_satisfaction_gate_present",
    "future_authority_satisfaction_gate_passed",
    "completed_stack_is_sufficient_for_future_satisfaction_gate",
    "authority_object_stack_complete",
    "all_required_future_authority_objects_instantiated",
    "terminal_closure_dependency_satisfied",
    "terminal_closure_authority_locked",
    "terminal_closure_locked_for_future_authority_snapshot",
    "explicit_transition_record_required_before_advancement",
    "gate_does_not_mutate_current_zero_snapshot",
    "gate_does_not_mutate_terminal_snapshot",
    "gate_does_not_open_future_snapshot_fork_gate_now",
    "gate_does_not_create_new_snapshot_now",
    "gate_does_not_issue_motion_picture",
    "gate_does_not_admit_media",
    "gate_does_not_create_release_candidate",
    "gate_does_not_advance_state",
)

for label in ("law", "status", "gate"):
    for field in required_gate_true:
        if not bool_value(docs[label], [field], default=False):
            raise SystemExit(f"{label} required true field false/missing: {field}")

for label in ("law", "status", "gate"):
    for field in (
        "authority_satisfied",
        "may_advance_now",
        "release_candidate_ready",
        "issued",
        "media_present",
        "future_snapshot_fork_gate_passed",
        "future_snapshot_fork_gate_open_now",
    ):
        if bool_value(docs[label], [field], default=False):
            raise SystemExit(f"{label} forbidden true value: {field}")

for obj in authority_objects:
    if not bool_value(obj, ["does_not_issue_motion_picture"], default=True):
        raise SystemExit("authority object may issue motion picture")
    if not bool_value(obj, ["does_not_admit_media"], default=True):
        raise SystemExit("authority object may admit media")
    if bool_value(obj, ["authority_satisfied"], default=False):
        raise SystemExit("authority object improperly sets authority_satisfied")
    if bool_value(obj, ["may_advance_now"], default=False):
        raise SystemExit("authority object improperly sets may_advance_now")

print("CINEMATICUM FUTURE AUTHORITY SATISFACTION GATE: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("GATE_SCOPE=FUTURE_COMPLETED_AUTHORITY_OBJECT_STACK_ONLY")
print(f"GATE_ID={GATE_ID}")
print(f"TERMINAL_AUTHORITY_OBJECT={TERMINAL_OBJECT}")
print(f"TERMINAL_INSTANTIATION_RECORD_ID={TERMINAL_INST}")
print("AUTHORITY_OBJECT_SLOT_COUNT=8")
print("ACCEPTED_DECISION_COUNT=8")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=8")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=8")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=0")
print("AUTHORITY_OBJECT_STACK_COMPLETE=true")
print("ALL_REQUIRED_FUTURE_AUTHORITY_OBJECTS_INSTANTIATED=true")
print("TERMINAL_CLOSURE_AUTHORITY_LOCKED=true")
print("FUTURE_AUTHORITY_SATISFACTION_GATE_PRESENT=true")
print("FUTURE_AUTHORITY_SATISFACTION_GATE_PASSED=true")
print("EXPLICIT_TRANSITION_RECORD_REQUIRED_BEFORE_ADVANCEMENT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("NEXT_REQUIRED_OBJECT=EXPLICIT_STATE_ADVANCEMENT_REQUEST")
PYVERIFYGATE
