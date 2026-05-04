#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")

PATHS = {
    "closure": ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json",
    "finality": ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL.json",
    "terminal": ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_TERMINAL_SEAL.json",
    "permanence": ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_PERMANENCE_SEAL.json",
    "law": ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_PERMANENCE_SEAL_LAW.json",
    "status": ROOT / "CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_PERMANENCE_SEAL_STATUS.json"
}

def load(name):
    p = PATHS[name]
    if not p.exists():
        raise AssertionError(f"missing required file: {p}")
    return json.loads(p.read_text(encoding="utf-8"))

def require(doc, key, value, name):
    actual = doc.get(key)
    if actual != value:
        raise AssertionError(f"{name}.{key} expected {value!r}, got {actual!r}")

def require_true(doc, key, name):
    require(doc, key, True, name)

def require_false(doc, key, name):
    require(doc, key, False, name)

closure = load("closure")
finality = load("finality")
terminal = load("terminal")
permanence = load("permanence")
law = load("law")
status = load("status")

for name, doc in [("closure", closure)]:
    require_true(doc, "admission_stack_closed", name)
    require_true(doc, "closure_seal_declared", name)
    require_false(doc, "enforcement_gate_passed", name)
    require_false(doc, "authority_satisfied", name)
    require_false(doc, "may_advance_now", name)
    require_false(doc, "release_candidate_ready", name)
    require_false(doc, "issued", name)
    require_false(doc, "media_present", name)

for name, doc in [("finality", finality)]:
    require_true(doc, "admission_stack_closed", name)
    require_true(doc, "closure_seal_declared", name)
    require_true(doc, "current_zero_admission_snapshot_final", name)
    require_false(doc, "current_zero_admission_snapshot_mutable", name)
    require_true(doc, "future_valid_admission_requests_allowed_under_law", name)
    require_true(doc, "future_valid_admission_requests_do_not_mutate_current_zero_snapshot", name)
    require_false(doc, "enforcement_gate_passed", name)
    require_false(doc, "authority_satisfied", name)
    require_false(doc, "may_advance_now", name)
    require_false(doc, "release_candidate_ready", name)
    require_false(doc, "issued", name)
    require_false(doc, "media_present", name)

for name, doc in [("terminal", terminal)]:
    require_true(doc, "admission_stack_closed", name)
    require_true(doc, "closure_seal_declared", name)
    require_true(doc, "finality_seal_declared", name)
    require_true(doc, "current_zero_admission_snapshot_final", name)
    require_true(doc, "current_zero_admission_snapshot_terminal", name)
    require_true(doc, "current_zero_admission_snapshot_closed_against_reclassification", name)
    require_false(doc, "current_zero_admission_snapshot_mutable", name)
    require_true(doc, "future_valid_admission_requests_allowed_under_law", name)
    require_true(doc, "future_valid_admission_requests_must_target_future_snapshot", name)
    require_true(doc, "future_valid_admission_requests_do_not_mutate_current_zero_snapshot", name)
    require_false(doc, "enforcement_gate_passed", name)
    require_false(doc, "authority_satisfied", name)
    require_false(doc, "may_advance_now", name)
    require_false(doc, "release_candidate_ready", name)
    require_false(doc, "issued", name)
    require_false(doc, "media_present", name)

for name, doc in [("permanence", permanence), ("status", status)]:
    require(doc, "current_state", "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED", name)
    require(doc, "permanence_scope", "CURRENT_ZERO_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_SNAPSHOT_ONLY", name)
    require(doc, "admission_stack_layer_count", 9, name)
    require_true(doc, "admission_stack_closed", name)
    require_true(doc, "closure_seal_declared", name)
    require_true(doc, "finality_seal_declared", name)
    require_true(doc, "terminal_seal_declared", name)
    require_true(doc, "current_zero_admission_snapshot_final", name)
    require_true(doc, "current_zero_admission_snapshot_terminal", name)
    require_true(doc, "current_zero_admission_snapshot_permanent", name)
    require_false(doc, "current_zero_admission_snapshot_mutable", name)
    require_true(doc, "current_zero_admission_snapshot_closed_against_reclassification", name)
    require_true(doc, "future_valid_admission_requests_allowed_under_law", name)
    require_true(doc, "future_valid_admission_requests_must_target_future_snapshot", name)
    require_true(doc, "future_valid_admission_requests_create_new_snapshot", name)
    require_true(doc, "future_valid_admission_requests_do_not_mutate_current_zero_snapshot", name)
    require_true(doc, "future_valid_admission_requests_do_not_mutate_terminal_snapshot", name)
    require_true(doc, "silent_snapshot_mutation_forbidden", name)
    require_true(doc, "terminal_snapshot_mutation_forbidden", name)
    require(doc, "live_admission_request_count", 0, name)
    require(doc, "valid_admission_request_count", 0, name)
    require(doc, "decision_record_count", 0, name)
    require(doc, "accepted_decision_count", 0, name)
    require(doc, "rejected_decision_count", 0, name)
    require(doc, "accepted_authority_object_count", 0, name)
    require(doc, "instantiated_authority_object_count", 0, name)
    require_true(doc, "no_unadjudicated_admission_records", name)
    require_false(doc, "enforcement_gate_passed", name)
    require_true(doc, "permanence_seal_does_not_satisfy_authority", name)
    require_true(doc, "permanence_seal_does_not_advance_state", name)
    require_true(doc, "permanence_seal_does_not_issue_motion_picture", name)
    require_true(doc, "permanence_seal_does_not_admit_media", name)
    require_true(doc, "permanence_seal_does_not_create_release_candidate", name)
    require_true(doc, "permanence_seal_does_not_create_new_snapshot_now", name)
    require_true(doc, "permanence_seal_does_not_mutate_current_zero_snapshot", name)
    require_true(doc, "permanence_seal_does_not_mutate_terminal_snapshot", name)
    require_true(doc, "permanence_seal_does_not_convert_zero_snapshot_into_authority", name)
    require_false(doc, "authority_satisfied", name)
    require_false(doc, "may_advance_now", name)
    require_false(doc, "release_candidate_ready", name)
    require_false(doc, "issued", name)
    require_false(doc, "media_present", name)

for key in [
    "requires_closure_seal",
    "requires_finality_seal",
    "requires_terminal_seal",
    "declares_current_zero_admission_snapshot_permanent",
    "forbids_silent_snapshot_mutation",
    "forbids_terminal_snapshot_mutation",
    "future_valid_admission_requests_allowed_under_law",
    "future_valid_admission_requests_must_target_future_snapshot",
    "future_valid_admission_requests_create_new_snapshot",
    "future_valid_admission_requests_do_not_mutate_current_zero_snapshot",
    "future_valid_admission_requests_do_not_mutate_terminal_snapshot",
    "permanence_does_not_satisfy_authority",
    "permanence_does_not_advance_state",
    "permanence_does_not_issue_motion_picture",
    "permanence_does_not_admit_media",
    "permanence_does_not_create_release_candidate",
    "permanence_does_not_create_new_snapshot_now",
    "permanence_does_not_convert_zero_snapshot_into_authority"
]:
    require_true(law, key, "law")

require_false(law, "declares_current_zero_admission_snapshot_mutable", "law")
require_false(law, "authority_satisfied", "law")
require_false(law, "may_advance_now", "law")
require_false(law, "release_candidate_ready", "law")
require_false(law, "issued", "law")
require_false(law, "media_present", "law")

print("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION PERMANENCE SEAL: PASS")
for key in [
    "current_state",
    "permanence_scope",
    "admission_stack_layer_count",
    "admission_stack_closed",
    "closure_seal_declared",
    "finality_seal_declared",
    "terminal_seal_declared",
    "current_zero_admission_snapshot_final",
    "current_zero_admission_snapshot_terminal",
    "current_zero_admission_snapshot_permanent",
    "current_zero_admission_snapshot_mutable",
    "current_zero_admission_snapshot_closed_against_reclassification",
    "future_valid_admission_requests_allowed_under_law",
    "future_valid_admission_requests_must_target_future_snapshot",
    "future_valid_admission_requests_create_new_snapshot",
    "future_valid_admission_requests_do_not_mutate_current_zero_snapshot",
    "future_valid_admission_requests_do_not_mutate_terminal_snapshot",
    "silent_snapshot_mutation_forbidden",
    "terminal_snapshot_mutation_forbidden",
    "live_admission_request_count",
    "valid_admission_request_count",
    "decision_record_count",
    "accepted_decision_count",
    "rejected_decision_count",
    "accepted_authority_object_count",
    "instantiated_authority_object_count",
    "no_unadjudicated_admission_records",
    "enforcement_gate_passed",
    "permanence_seal_does_not_satisfy_authority",
    "permanence_seal_does_not_advance_state",
    "permanence_seal_does_not_issue_motion_picture",
    "permanence_seal_does_not_admit_media",
    "permanence_seal_does_not_create_release_candidate",
    "permanence_seal_does_not_create_new_snapshot_now",
    "permanence_seal_does_not_mutate_current_zero_snapshot",
    "permanence_seal_does_not_mutate_terminal_snapshot",
    "permanence_seal_does_not_convert_zero_snapshot_into_authority",
    "authority_satisfied",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present"
]:
    value = permanence[key]
    if isinstance(value, bool):
        value = str(value).lower()
    print(f"{key.upper()}={value}")
PY
