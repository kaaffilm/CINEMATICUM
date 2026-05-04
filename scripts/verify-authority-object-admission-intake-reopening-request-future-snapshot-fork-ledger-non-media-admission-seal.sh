#!/usr/bin/env bash
set -euo pipefail

STATUS="CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_MEDIA_ADMISSION_SEAL_STATUS.json"
OBJECT="CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_MEDIA_ADMISSION_SEAL.json"
LAW="CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_MEDIA_ADMISSION_SEAL_LAW.json"

test -f "$STATUS"
test -f "$OBJECT"
test -f "$LAW"
test -f "CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_RELEASE_CANDIDATE_SEAL_STATUS.json"

python3 - <<'PY'
import json
from pathlib import Path

status = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_MEDIA_ADMISSION_SEAL_STATUS.json").read_text())
obj = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_MEDIA_ADMISSION_SEAL.json").read_text())
law = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_MEDIA_ADMISSION_SEAL_LAW.json").read_text())
prev = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_RELEASE_CANDIDATE_SEAL_STATUS.json").read_text())

assert status["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert status["non_media_admission_scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"

required_true = [
    "future_snapshot_fork_ledger_present",
    "future_snapshot_fork_ledger_terminal_closure_sealed",
    "future_snapshot_fork_ledger_non_issuance_sealed",
    "future_snapshot_fork_ledger_non_authority_satisfaction_sealed",
    "future_snapshot_fork_ledger_non_advancement_sealed",
    "future_snapshot_fork_ledger_non_release_candidate_sealed",
    "future_snapshot_fork_ledger_non_media_admission_sealed",
    "current_zero_ledger_media_admission_blocked",
    "current_zero_ledger_state_unchanged",
    "terminal_closure_does_not_admit_media",
    "non_issuance_does_not_admit_media",
    "non_authority_satisfaction_does_not_admit_media",
    "non_advancement_does_not_admit_media",
    "non_release_candidate_does_not_admit_media",
    "non_media_admission_seal_passed_for_current_zero_ledger",
    "non_media_admission_artifact_required_for_future_fork",
    "non_media_admission_seal_does_not_open_future_fork_gate",
    "non_media_admission_seal_does_not_create_new_snapshot",
    "non_media_admission_seal_does_not_mutate_current_snapshot",
    "non_media_admission_seal_does_not_mutate_permanent_ledger",
    "non_media_admission_seal_does_not_satisfy_authority",
    "non_media_admission_seal_does_not_advance_state",
    "non_media_admission_seal_does_not_issue_motion_picture",
    "non_media_admission_seal_does_not_create_release_candidate",
    "non_media_admission_seal_does_not_admit_media",
    "future_valid_fork_must_establish_media_admission_independently",
    "future_valid_fork_media_admission_must_target_new_snapshot",
]
for k in required_true:
    assert status[k] is True, k

required_false = [
    "current_zero_ledger_media_present",
    "current_zero_ledger_release_candidate_ready",
    "current_zero_ledger_may_advance_now",
    "current_zero_ledger_authority_satisfied",
    "current_zero_ledger_issued",
    "future_snapshot_fork_gate_passed_now",
    "future_snapshot_fork_gate_open_now",
    "non_media_admission_seal_passed_for_future_fork",
    "non_media_admission_artifact_present_for_future_fork",
    "private_access_required",
    "network_required_after_clone",
    "media_or_model_payload_present",
    "authority_satisfied",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present",
]
for k in required_false:
    assert status[k] is False, k

assert status["future_snapshot_fork_record_count"] == 0
assert status["new_snapshot_record_count"] == 0

assert prev["future_snapshot_fork_ledger_non_release_candidate_sealed"] is True
assert prev["release_candidate_ready"] is False
assert prev["media_present"] is False
assert prev["issued"] is False

assert obj["scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
assert obj["seal"] == "NON_MEDIA_ADMISSION"
assert obj["does_not_admit_media"] is True
assert obj["does_not_issue_motion_picture"] is True
assert obj["does_not_create_release_candidate"] is True
assert obj["does_not_advance_state"] is True
assert obj["does_not_satisfy_authority"] is True
assert obj["future_valid_fork_must_establish_media_admission_independently"] is True

assert law["scope"] == "CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY"
assert law["private_access_required"] is False
assert law["network_required_after_clone"] is False
assert law["media_or_model_payload_present"] is False

print("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER NON-MEDIA-ADMISSION SEAL: PASS")
for key in [
    "current_state",
    "non_media_admission_scope",
    "future_snapshot_fork_ledger_present",
    "future_snapshot_fork_ledger_terminal_closure_sealed",
    "future_snapshot_fork_ledger_non_issuance_sealed",
    "future_snapshot_fork_ledger_non_authority_satisfaction_sealed",
    "future_snapshot_fork_ledger_non_advancement_sealed",
    "future_snapshot_fork_ledger_non_release_candidate_sealed",
    "future_snapshot_fork_ledger_non_media_admission_sealed",
    "current_zero_ledger_media_admission_blocked",
    "current_zero_ledger_media_present",
    "current_zero_ledger_release_candidate_ready",
    "current_zero_ledger_may_advance_now",
    "current_zero_ledger_authority_satisfied",
    "current_zero_ledger_issued",
    "current_zero_ledger_state_unchanged",
    "future_snapshot_fork_gate_passed_now",
    "future_snapshot_fork_gate_open_now",
    "future_snapshot_fork_record_count",
    "new_snapshot_record_count",
    "non_media_admission_seal_passed_for_current_zero_ledger",
    "non_media_admission_seal_passed_for_future_fork",
    "non_media_admission_artifact_required_for_future_fork",
    "non_media_admission_artifact_present_for_future_fork",
    "non_media_admission_seal_does_not_open_future_fork_gate",
    "non_media_admission_seal_does_not_create_new_snapshot",
    "non_media_admission_seal_does_not_mutate_current_snapshot",
    "non_media_admission_seal_does_not_mutate_permanent_ledger",
    "non_media_admission_seal_does_not_satisfy_authority",
    "non_media_admission_seal_does_not_advance_state",
    "non_media_admission_seal_does_not_issue_motion_picture",
    "non_media_admission_seal_does_not_create_release_candidate",
    "non_media_admission_seal_does_not_admit_media",
    "future_valid_fork_must_establish_media_admission_independently",
    "future_valid_fork_media_admission_must_target_new_snapshot",
    "private_access_required",
    "network_required_after_clone",
    "media_or_model_payload_present",
    "authority_satisfied",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present",
]:
    v = status[key]
    print(f"{key.upper()}={str(v).lower() if isinstance(v, bool) else v}")
PY
