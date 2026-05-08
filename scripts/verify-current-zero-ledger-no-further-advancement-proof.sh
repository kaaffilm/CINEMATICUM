#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
import pathlib
import sys

CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
ACTIVE_TARGET = 'RELEASE_CANDIDATE_READY'

ROOT = pathlib.Path(".")
paths = {
    "case_state": ROOT / "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json",
    "proof": ROOT / "CINEMATICUM_CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF.json",
    "law": ROOT / "CINEMATICUM_CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF_LAW.json",
    "status": ROOT / "CASES/CASE_001_THE_LAST_RENDER/CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF_STATUS.json",
    "stop_rule": ROOT / "CINEMATICUM_NON_STAR_SEAL_REDUNDANCY_STOP_RULE.json",
    "stop_rule_law": ROOT / "CINEMATICUM_NON_STAR_SEAL_REDUNDANCY_STOP_RULE_LAW.json",
    "zero_index": ROOT / "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_ZERO_PERIMETER_COMPLETION_INDEX.json",
}

missing = [str(p) for p in paths.values() if not p.exists()]
if missing:
    raise AssertionError("missing required files: " + ", ".join(missing))

def load(name):
    with paths[name].open(encoding="utf-8") as f:
        return json.load(f)

def flat_contains(obj, needle):
    return needle in json.dumps(obj, sort_keys=True)

def get_any(obj, names, default=None):
    if isinstance(names, str):
        names = [names]
    stack = [obj]
    lowered = {n.lower() for n in names}
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if str(k).lower() in lowered:
                    return v
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return default

def bool_value(obj, names, default=False):
    v = get_any(obj, names, default)
    return bool(v)

case_state = load("case_state")
proof = load("proof")
law = load("law")
status = load("status")
stop_rule = load("stop_rule")
stop_rule_law = load("stop_rule_law")
zero_index = load("zero_index")

index = json.loads(pathlib.Path("CINEMATICUM_CURRENT_STATE_INDEX.json").read_text(encoding="utf-8"))
case = json.loads(pathlib.Path("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json").read_text(encoding="utf-8"))
assert proof["current_state"] == TARGET, "record current state mismatch"
assert index["active_case_states"][CASE_ID] == ACTIVE_TARGET, "active index current state mismatch"
assert case["current_state"] == ACTIVE_TARGET, "active case current state mismatch"
assert proof.get("object_type") == "CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF", proof.get("object_type")
assert proof.get("schema_version") == "cinematicum.current_zero_ledger_no_further_advancement_proof.v1", proof.get("schema_version")
assert law.get("object_type") == "CINEMATICUM_CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF_LAW", law.get("object_type")
assert status.get("object_type") == "CINEMATICUM_CASE_CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF_STATUS", status.get("object_type")

assert proof.get("issued") is False, "proof must not issue"
assert proof.get("media_present") is False, "proof must not admit media"
assert proof.get("release_candidate_ready") is False, "proof must not create release candidate"
assert proof.get("outsider_replay_passed") is False, "proof must not pass outsider replay"

assert status.get("issued") is False, "status must not issue"
assert status.get("media_present") is False, "status must not admit media"
assert status.get("release_candidate_ready") is False, "status must not create release candidate"

assert flat_contains(stop_rule, "CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF") or flat_contains(stop_rule_law, "CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF"), "PR67 stop rule does not route to PR68 object"
assert flat_contains(zero_index, "OPEN_REAL_CASE_AUTHORITY_INTAKE") or flat_contains(stop_rule, "OPEN_REAL_CASE_AUTHORITY_INTAKE") or flat_contains(stop_rule_law, "OPEN_REAL_CASE_AUTHORITY_INTAKE"), "real intake route missing"

for obj_name, obj in {
    "proof": proof,
    "law": law,
    "status": status,
}.items():
    for key in (
        "authority_satisfied",
        "may_advance_now",
        "release_candidate_ready",
        "issued",
        "media_present",
        "future_snapshot_fork_gate_open_now",
        "new_snapshot_created_now",
        "new_snapshot_record_count",
    ):
        value = get_any(obj, key, None)
        if value is True:
            raise AssertionError(f"{obj_name}.{key} unexpectedly true")
        if key == "new_snapshot_record_count" and value not in (None, 0):
            raise AssertionError(f"{obj_name}.{key} unexpectedly nonzero: {value}")

print("CINEMATICUM CURRENT ZERO LEDGER NO FURTHER ADVANCEMENT PROOF: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("PROOF_SCOPE=POST_NON_STAR_SEAL_REDUNDANCY_STOP_RULE_CURRENT_ZERO_LEDGER_ONLY")
print("CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF_PRESENT=true")
print("CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF_SEALED=true")
print("OBJECT_IS_NON_STAR_SEAL=false")
print("FUTURE_WORK_MUST_ROUTE_TO_REAL_CASE_AUTHORITY_INTAKE=true")
print("TRANSITION_REQUEST_OBJECT=OPEN_REAL_CASE_AUTHORITY_INTAKE")
print("PROOF_DOES_NOT_ADVANCE_STATE=true")
print("PROOF_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("PROOF_DOES_NOT_ADMIT_MEDIA=true")
print("PROOF_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true")
print("PROOF_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
