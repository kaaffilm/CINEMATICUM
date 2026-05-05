#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path
from typing import Any, Iterable

CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
REQUEST_ID = "REQ_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"
VALIDATION_RECORD_ID = "VAL_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"
DECISION_RECORD_ID = "DEC_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"
INSTANTIATION_RECORD_ID = "INST_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"
AUTHORITY_SLOT_ID = "director_final_cut_authority"
AUTHORITY_OBJECT = "DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT"

PATHS = {
    "law": Path("CINEMATICUM_FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_INSTANTIATION_RECORD_LAW.json"),
    "status": Path("CASES/CASE_001_THE_LAST_RENDER/FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_INSTANTIATION_RECORD_STATUS.json"),
    "instantiation": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_INSTANTIATION_RECORDS/INST_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json"),
    "authority_object": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json"),
    "decision": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_RECORDS/DEC_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json"),
    "validation": Path("CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_VALIDATION_RECORDS/VAL_001_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json"),
    "request_status": Path("CASES/CASE_001_THE_LAST_RENDER/FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_ADMISSION_REQUEST_STATUS.json"),
    "decision_status": Path("CASES/CASE_001_THE_LAST_RENDER/FIRST_FUTURE_DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT_ADMISSION_DECISION_RECORD_STATUS.json"),
}

def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def walk_values(node: Any) -> Iterable[Any]:
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from walk_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_values(value)

def walk_items(node: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key), value
            yield from walk_items(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_items(value)

def norm(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)

def contains_value(node: Any, expected: Any) -> bool:
    expected_s = norm(expected)
    return any(norm(value) == expected_s for value in walk_values(node))

def find_key_value(node: Any, names: Iterable[str]) -> Any:
    wanted = {name.lower() for name in names}
    for key, value in walk_items(node):
        if key.lower() in wanted:
            return value
    raise KeyError(",".join(names))

def bool_value(node: Any, names: Iterable[str], default: bool | None = None) -> bool:
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

def int_value(node: Any, names: Iterable[str], default: int | None = None) -> int:
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

docs = {name: load_json(path) for name, path in PATHS.items()}

for label, doc in docs.items():
    for expected in (
        CURRENT_STATE,
        AUTHORITY_SLOT_ID,
        AUTHORITY_OBJECT,
    ):
        if expected == CURRENT_STATE and label in {"authority_object"}:
            continue
        if not contains_value(doc, expected):
            raise SystemExit(f"{label} missing expected value: {expected}")

for label in ("law", "status", "instantiation"):
    for expected in (
        REQUEST_ID,
        VALIDATION_RECORD_ID,
        DECISION_RECORD_ID,
        INSTANTIATION_RECORD_ID,
        AUTHORITY_SLOT_ID,
        AUTHORITY_OBJECT,
    ):
        if not contains_value(docs[label], expected):
            raise SystemExit(f"{label} missing expected value: {expected}")

if not contains_value(docs["decision"], DECISION_RECORD_ID):
    raise SystemExit("decision record id mismatch")
if not contains_value(docs["validation"], VALIDATION_RECORD_ID):
    raise SystemExit("validation record id mismatch")
if not contains_value(docs["decision"], REQUEST_ID):
    raise SystemExit("decision request id mismatch")
if not contains_value(docs["validation"], REQUEST_ID):
    raise SystemExit("validation request id mismatch")

request_targets_future_snapshot = bool_value(
    docs["instantiation"],
    ["REQUEST_TARGETS_FUTURE_SNAPSHOT", "request_targets_future_snapshot"],
    default=True,
)
request_schema_valid = bool_value(
    docs["validation"],
    ["REQUEST_SCHEMA_VALID", "request_schema_valid"],
    default=True,
)
slot_identity_valid = bool_value(
    docs["validation"],
    ["SLOT_IDENTITY_VALID", "slot_identity_valid"],
    default=True,
)
authority_object_identity_valid = bool_value(
    docs["validation"],
    ["AUTHORITY_OBJECT_IDENTITY_VALID", "authority_object_identity_valid"],
    default=True,
)
decision_accepts_request = bool_value(
    docs["decision"],
    ["DECISION_RECORD_ACCEPTS_REQUEST", "decision_record_accepts_request", "accepts_request"],
    default=True,
)
instantiates_authority_object = bool_value(
    docs["instantiation"],
    [
        "INSTANTIATION_RECORD_INSTANTIATES_AUTHORITY_OBJECT",
        "instantiation_record_instantiates_authority_object",
        "instantiates_authority_object",
    ],
    default=True,
)

if not request_targets_future_snapshot:
    raise SystemExit("request does not target future snapshot")
if not request_schema_valid:
    raise SystemExit("request schema not valid")
if not slot_identity_valid:
    raise SystemExit("slot identity not valid")
if not authority_object_identity_valid:
    raise SystemExit("authority object identity not valid")
if not decision_accepts_request:
    raise SystemExit("decision record does not accept request")
if not instantiates_authority_object:
    raise SystemExit("instantiation record does not instantiate authority object")

accepted_decision_count = int_value(
    docs["status"],
    ["ACCEPTED_DECISION_COUNT", "accepted_decision_count"],
    default=1,
)
accepted_authority_object_count = int_value(
    docs["status"],
    ["ACCEPTED_AUTHORITY_OBJECT_COUNT", "accepted_authority_object_count"],
    default=1,
)
instantiated_authority_object_count = int_value(
    docs["status"],
    ["INSTANTIATED_AUTHORITY_OBJECT_COUNT", "instantiated_authority_object_count"],
    default=1,
)

if accepted_decision_count != 1:
    raise SystemExit("accepted decision count mismatch")
if accepted_authority_object_count != 1:
    raise SystemExit("accepted authority object count mismatch")
if instantiated_authority_object_count != 1:
    raise SystemExit("instantiated authority object count mismatch")

future_snapshot_fork_gate_passed = bool_value(
    docs["status"],
    ["FUTURE_SNAPSHOT_FORK_GATE_PASSED", "future_snapshot_fork_gate_passed"],
    default=False,
)
future_snapshot_fork_gate_open_now = bool_value(
    docs["status"],
    ["FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW", "future_snapshot_fork_gate_open_now"],
    default=False,
)
authority_satisfied = bool_value(
    docs["status"],
    ["AUTHORITY_SATISFIED", "authority_satisfied"],
    default=False,
)
may_advance_now = bool_value(
    docs["status"],
    ["MAY_ADVANCE_NOW", "may_advance_now"],
    default=False,
)
release_candidate_ready = bool_value(
    docs["status"],
    ["RELEASE_CANDIDATE_READY", "release_candidate_ready"],
    default=False,
)
issued = bool_value(
    docs["status"],
    ["ISSUED", "issued"],
    default=False,
)
media_present = bool_value(
    docs["status"],
    ["MEDIA_PRESENT", "media_present"],
    default=False,
)

for name, value in {
    "future snapshot fork gate passed": future_snapshot_fork_gate_passed,
    "future snapshot fork gate open now": future_snapshot_fork_gate_open_now,
    "authority satisfied": authority_satisfied,
    "may advance now": may_advance_now,
    "release candidate ready": release_candidate_ready,
    "issued": issued,
    "media present": media_present,
}.items():
    if value:
        raise SystemExit(f"forbidden true value: {name}")

print("CINEMATICUM FIRST FUTURE DIRECTOR FINAL CUT AUTHORITY OBJECT INSTANTIATION RECORD: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("INSTANTIATION_SCOPE=FUTURE_VALID_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUESTS_ONLY")
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
print("ACCEPTED_DECISION_COUNT=1")
print("ACCEPTED_AUTHORITY_OBJECT_COUNT=1")
print("INSTANTIATED_AUTHORITY_OBJECT_COUNT=1")
print("FUTURE_SNAPSHOT_FORK_GATE_PASSED=false")
print("FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW=false")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
