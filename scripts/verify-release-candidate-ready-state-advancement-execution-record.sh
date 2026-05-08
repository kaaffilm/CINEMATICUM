#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest tests/test_release_candidate_ready_state_advancement_execution_record.py

python3 - <<'PY'
import json
from pathlib import Path

record = json.loads(Path("CINEMATICUM_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_EXECUTION_RECORD.json").read_text())

ordered_keys = [
    "current_state",
    "execution_scope",
    "execution_object",
    "execution_record_id",
    "prior_decision_object",
    "prior_decision_id",
    "request_object",
    "request_id",
    "requested_next_state",
    "required_prior_object",
    "outsider_replay_passed",
    "admissibility_verdict_present",
    "admissibility_verdict_result",
    "terminal_closure_present",
    "release_candidate_ready_state_advancement_request_present",
    "release_candidate_ready_state_advancement_decision_record_present",
    "decision_accepts_request",
    "decision_authorizes_state_mutation",
    "authority_satisfied_for_transition",
    "state_mutation_execution_authorized",
    "current_state_index_mutation_authorized",
    "current_state_index_change_deferred_to_next_object",
    "current_state_index_still_points_to_from_state",
    "authority_satisfied",
    "may_advance_now",
    "release_candidate_ready",
    "issued",
    "media_present",
    "current_state_unchanged",
    "next_required_object",
]

print("CINEMATICUM RELEASE CANDIDATE READY STATE ADVANCEMENT EXECUTION RECORD: PASS")
for key in ordered_keys:
    value = record[key]
    if isinstance(value, bool):
        value = str(value).lower()
    print(f"{key.upper()}={value}")
PY
