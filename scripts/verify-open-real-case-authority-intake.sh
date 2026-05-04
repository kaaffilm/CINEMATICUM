#!/usr/bin/env bash
set -euo pipefail

# Do not bind to the prior proof status JSON schema. Its verifier is the contract.
bash scripts/verify-current-zero-ledger-no-further-advancement-proof.sh >/dev/null

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")
CASE = ROOT / "CASES" / "CASE_001_THE_LAST_RENDER"
EXPECTED_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

def load(path):
    p = Path(path)
    assert p.exists(), f"missing {path}"
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def first(record, *keys):
    for key in keys:
        if key in record:
            return record[key]
    raise AssertionError(f"none of keys {keys} present; available={sorted(record.keys())}")

def require_true(record, *keys):
    v = first(record, *keys)
    assert v is True, f"{keys}={v!r}"

def require_false(record, *keys):
    v = first(record, *keys)
    assert v is False, f"{keys}={v!r}"

def require_eq(record, expected, *keys):
    v = first(record, *keys)
    assert v == expected, f"{keys}={v!r}, expected={expected!r}"

current = load(CASE / "CURRENT_CASE_STATE.json")
obj = load("CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE.json")
law = load("CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE_LAW.json")
status = load(CASE / "OPEN_REAL_CASE_AUTHORITY_INTAKE_STATUS.json")

current_state = first(
    current,
    "active_current_state",
    "current_active_state",
    "current_state",
    "state",
    "state_id",
)
assert current_state == EXPECTED_STATE, current_state

for record in (current,):
    for key in ("issued", "release_candidate_ready", "media_present"):
        if key in record:
            assert record[key] is False, f"{key}={record[key]!r}"

require_eq(obj, "CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE", "object_type")
require_eq(obj, "cinematicum.open_real_case_authority_intake.v1", "schema_version")
require_eq(obj, "CASE_001_THE_LAST_RENDER", "case_id")
require_eq(obj, EXPECTED_STATE, "current_state")
require_eq(obj, "CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF", "opened_after_object", "prior_required_object")
require_eq(obj, "OPEN_REAL_CASE_AUTHORITY_INTAKE", "intake_object", "transition_request_object")
require_eq(obj, "REAL_CASE_AUTHORITY_OBJECTS_ONLY", "intake_scope", "scope")

for keys in [
    ("real_case_authority_intake_open", "intake_open"),
    ("authority_object_admission_requests_allowed", "admission_requests_allowed"),
    ("negative_seal_route_closed",),
    ("additional_non_star_seals_default_forbidden",),
    ("object_opens_intake_only",),
    ("object_does_not_satisfy_authority",),
    ("object_does_not_advance_state",),
    ("object_does_not_issue_motion_picture",),
    ("object_does_not_admit_media",),
    ("object_does_not_create_release_candidate",),
    ("object_does_not_create_new_snapshot",),
    ("object_does_not_reopen_current_snapshot",),
]:
    require_true(obj, *keys)

for keys in [
    ("object_is_non_star_seal",),
    ("object_is_negative_capability_seal",),
    ("authority_satisfied",),
    ("may_advance_now",),
    ("release_candidate_ready",),
    ("issued",),
    ("media_present",),
]:
    require_false(obj, *keys)

require_eq(law, "CINEMATICUM_OPEN_REAL_CASE_AUTHORITY_INTAKE_LAW", "object_type")
require_eq(law, "cinematicum.open_real_case_authority_intake_law.v1", "schema_version")
require_eq(
    law,
    "POST_CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF_REAL_AUTHORITY_INTAKE_ONLY",
    "law_scope",
    "scope",
)
require_eq(law, "CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF", "trigger_object")
require_eq(law, "OPEN_REAL_CASE_AUTHORITY_INTAKE", "allowed_transition_request_object", "transition_request_object")

for keys in [
    ("real_case_authority_intake_may_open",),
    ("silent_intake_opening_forbidden",),
    ("future_real_authority_objects_must_satisfy_authority_independently",),
    ("future_media_admission_must_be_established_independently",),
    ("intake_opening_does_not_satisfy_authority",),
    ("intake_opening_does_not_advance_state",),
    ("intake_opening_does_not_issue_motion_picture",),
    ("intake_opening_does_not_admit_media",),
    ("intake_opening_does_not_create_release_candidate",),
    ("intake_opening_does_not_reopen_current_snapshot",),
    ("intake_opening_does_not_create_new_snapshot",),
]:
    require_true(law, *keys)

for keys in [
    ("authority_satisfied",),
    ("may_advance_now",),
    ("release_candidate_ready",),
    ("issued",),
    ("media_present",),
]:
    require_false(law, *keys)

require_eq(status, "CINEMATICUM_CASE_OPEN_REAL_CASE_AUTHORITY_INTAKE_STATUS", "object_type")
require_eq(status, "cinematicum.case_open_real_case_authority_intake_status.v1", "schema_version")
require_eq(status, "CASE_001_THE_LAST_RENDER", "case_id")
require_eq(status, EXPECTED_STATE, "current_state")

for keys in [
    ("open_real_case_authority_intake_present", "present"),
    ("open_real_case_authority_intake_sealed", "sealed"),
    ("current_zero_ledger_no_further_advancement_proof_required", "prior_proof_required"),
    ("current_zero_ledger_no_further_advancement_proof_present", "prior_proof_present"),
    ("current_zero_ledger_no_further_advancement_proof_sealed", "prior_proof_sealed"),
    ("real_case_authority_intake_open", "intake_open"),
    ("authority_object_admission_requests_allowed", "admission_requests_allowed"),
    ("negative_seal_route_closed",),
    ("future_work_routes_to_real_case_authority_intake",),
    ("intake_opening_does_not_satisfy_authority",),
    ("intake_opening_does_not_advance_state",),
    ("intake_opening_does_not_issue_motion_picture",),
    ("intake_opening_does_not_admit_media",),
    ("intake_opening_does_not_create_release_candidate",),
    ("intake_opening_does_not_reopen_current_snapshot",),
    ("intake_opening_does_not_create_new_snapshot",),
]:
    require_true(status, *keys)

for keys in [
    ("authority_satisfied",),
    ("may_advance_now",),
    ("release_candidate_ready",),
    ("issued",),
    ("media_present",),
]:
    require_false(status, *keys)

for key in ("valid_authority_object_count", "accepted_authority_object_count", "instantiated_authority_object_count"):
    if key in status:
        assert status[key] == 0, f"{key}={status[key]!r}"

require_eq(status, "REAL_CASE_AUTHORITY_INTAKE", "next_required_phase")
require_eq(status, "SUBMIT_REAL_CASE_AUTHORITY_OBJECTS", "next_required_object")

print("CINEMATICUM OPEN REAL CASE AUTHORITY INTAKE: PASS")
print("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("INTAKE_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY")
print("OPEN_REAL_CASE_AUTHORITY_INTAKE_PRESENT=true")
print("OPEN_REAL_CASE_AUTHORITY_INTAKE_SEALED=true")
print("REAL_CASE_AUTHORITY_INTAKE_OPEN=true")
print("AUTHORITY_OBJECT_ADMISSION_REQUESTS_ALLOWED=true")
print("NEGATIVE_SEAL_ROUTE_CLOSED=true")
print("OBJECT_IS_NON_STAR_SEAL=false")
print("OBJECT_IS_NEGATIVE_CAPABILITY_SEAL=false")
print("INTAKE_OPENING_DOES_NOT_SATISFY_AUTHORITY=true")
print("INTAKE_OPENING_DOES_NOT_ADVANCE_STATE=true")
print("INTAKE_OPENING_DOES_NOT_ISSUE_MOTION_PICTURE=true")
print("INTAKE_OPENING_DOES_NOT_ADMIT_MEDIA=true")
print("INTAKE_OPENING_DOES_NOT_CREATE_RELEASE_CANDIDATE=true")
print("INTAKE_OPENING_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true")
print("INTAKE_OPENING_DOES_NOT_CREATE_NEW_SNAPSHOT=true")
print("AUTHORITY_SATISFIED=false")
print("MAY_ADVANCE_NOW=false")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY
