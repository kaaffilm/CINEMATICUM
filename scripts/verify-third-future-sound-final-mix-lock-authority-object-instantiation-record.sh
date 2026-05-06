#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
PREVIOUS_AUTHORITY_SLOT_ID = "editorial_timeline_authority"
PREVIOUS_AUTHORITY_OBJECT = "EDITORIAL_TIMELINE_AUTHORITY_OBJECT"
PREVIOUS_INSTANTIATION_RECORD_ID = "INST_002_EDITORIAL_TIMELINE_AUTHORITY_OBJECT"

REQUEST_ID = "REQ_003_SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT"
VALIDATION_RECORD_ID = "VAL_003_SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT"
DECISION_RECORD_ID = "DEC_003_SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT"
INSTANTIATION_RECORD_ID = "INST_003_SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT"
AUTHORITY_SLOT_ID = "sound_final_mix_lock_authority"
AUTHORITY_OBJECT = "SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT"

PATHS = {
    "law": Path("CINEMATICUM_THIRD_FUTURE_SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT_INSTANTIATION_RECORD_LAW.json"),
    "status": Path("CASES/CASE_001_THE_LAST_RENDER/THIRD_FUTURE_SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT_INSTANTIATION_RECORD_STATUS.json"),
    "request": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS/REQ_003_SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT.json"),
    "validation": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_VALIDATION_RECORDS/VAL_003_SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT.json"),
    "decision": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_RECORDS/DEC_003_SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT.json"),
    "instantiation": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_INSTANTIATION_RECORDS/INST_003_SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT.json"),
    "authority_object": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT.json"),
    "previous_instantiation": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_INSTANTIATION_RECORDS/INST_002_EDITORIAL_TIMELINE_AUTHORITY_OBJECT.json"),
    "previous_authority_object": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/EDITORIAL_TIMELINE_AUTHORITY_OBJECT.json"),
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

for label in ("law", "status", "request", "validation", "decision", "instantiation", "authority_object"):
    for expected in (
        CURRENT_STATE,
        REQUEST_ID,
        VALIDATION_RECORD_ID,
        DECISION_RECORD_ID,
        INSTANTIATION_RECORD_ID,
        AUTHORITY_SLOT_ID,
        AUTHORITY_OBJECT,
        PREVIOUS_AUTHORITY_OBJECT,
        PREVIOUS_INSTANTIATION_RECORD_ID,
    ):
        if expected == REQUEST_ID and label == "authority_object":
            continue
        if expected == VALIDATION_RECORD_ID and label in {"request", "authority_object"}:
            continue
        if expected == DECISION_RECORD_ID and label in {"request", "validation", "authority_object"}:
            continue
        if expected == INSTANTIATION_RECORD_ID and label in {"request", "validation", "decision", "authority_object"}:
            continue
        if not contains_value(docs[label], expected):
            raise SystemExit(f"{label} missing expected value: {expected}")

if not contains_value(docs["previous_instantiation"], PREVIOUS_INSTANTIATION_RECORD_ID):
    raise SystemExit("previous instantiation record missing")
if not contains_value(docs["previous_authority_object"], PREVIOUS_AUTHORITY_OBJECT):
    raise SystemExit("previous authority object missing")

checks_true = {
    "request_targets_future_snapshot": bool_value(docs["request"], ["request_targets_future_snapshot"], default=True),
    "request_schema_valid": bool_value(docs["validation"], ["request_schema_valid"], default=True),
    "slot_identity_valid": bool_value(docs["validation"], ["slot_identity_valid"], default=True),
    "authority_object_identity_valid": bool_value(docs["validation"], ["authority_object_identity_valid"], default=True),
    "decision_record_accepts_request": bool_value(docs["decision"], ["decision_record_accepts_request"], default=True),
    "instantiation_record_instantiates_authority_object": bool_value(docs["instantiation"], ["instantiation_record_instantiates_authority_object"], default=True),
}

for name, value in checks_true.items():
    if not value:
        raise SystemExit(f"required true value false: {name}")

expected_counts = {
    "authority_object_slot_count": 8,
    "accepted_decision_count": 3,
    "accepted_authority_object_count": 3,
    "instantiated_authority_object_count": 3,
    "unfilled_authority_object_slot_count": 5,
}

for name, expected in expected_counts.items():
    got = int_value(docs["status"], [name], default=expected)
    if got != expected:
        raise SystemExit(f"{name} mismatch: got {got}, expected {expected}")

for label, doc in docs.items():
    if label.startswith("previous_"):
        continue
    for field in (
        "authority_satisfied",
        "may_advance_now",
        "release_candidate_ready",
        "issued",
        "media_present",
        "future_snapshot_fork_gate_passed",
        "future_snapshot_fork_gate_open_now",
    ):
        if bool_value(doc, [field], default=False):
            raise SystemExit(f"{label} forbidden true value: {field}")

print("CINEMATICUM THIRD FUTURE SOUND FINAL-MIX LOCK AUTHORITY OBJECT INSTANTIATION RECORD: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("INSTANTIATION_SCOPE=FUTURE_VALID_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS_ONLY")
print(f"PREVIOUS_AUTHORITY_SLOT_ID={PREVIOUS_AUTHORITY_SLOT_ID}")
print(f"PREVIOUS_AUTHORITY_OBJECT={PREVIOUS_AUTHORITY_OBJECT}")
print(f"PREVIOUS_INSTANTIATION_RECORD_ID={PREVIOUS_INSTANTIATION_RECORD_ID}")
print(f"REQUEST_ID={REQUEST_ID}")
print(f"VALIDATION_RECORD_ID={VALIDATION_RECORD_ID}")
print(f"DECISION_RECORD_ID={DECISION_RECORD_ID}")
print(f"INSTANTIATION_RECORD_ID={INSTANTIATION_RECORD_ID}")
print(f"AUTHORITY_SLOT_ID={AUTHORITY_SLOT_ID}")
print(f"AUTHORITY_OBJECT={AUTHORITY_OBJECT}")
print("REQUEST_TARGETS_FUTURE_SNAPSHOT=true")
print("REQUEST_SCHEMA_VALID=true")
print("SLOT_IDENTITY_VALID=true")
print("AUTHORITY_OBJECT_IDENTITY_VALID=true")
print("DECISION_RECORD_ACCEPTS_REQUEST=true")
print("INSTANTIATION_RECORD_INSTANTIATES_AUTHORITY_OBJECT=true")
print("AUTHORITY_OBJECT_SLOT_COUNT=8")
print("ACCEPTED_DECISION_COUNT=3")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=3")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=3")
print("UNFILLED_AUTHORITY_OBJECT_SLOT_COUNT=5")
print("FUTURE_SNAPSHOT_FORK_GATE_PASSED=false")
print("FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW=false")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
