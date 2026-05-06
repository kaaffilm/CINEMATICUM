#!/usr/bin/env bash
set -euo pipefail

python3 scripts/regenerate-object-registry.py --write >/dev/null
python3 -m unittest tests/test_release_candidate_outsider_replay_passage_record.py

python3 - <<'PY'
import json
from pathlib import Path

obj = json.loads(Path("CINEMATICUM_RELEASE_CANDIDATE_OUTSIDER_REPLAY_PASSAGE_RECORD.json").read_text())

required_true = [
    "release_candidate_planning_perimeter_complete",
    "all_required_release_candidate_gap_objects_present",
    "release_candidate_outsider_replay_execution_record_present",
    "outsider_replay_execution_record_present",
    "outsider_replay_execution_completed",
    "outsider_replay_passage_record_present",
    "outsider_replay_passage_declared",
    "outsider_replay_passed",
    "fresh_checkout_can_verify",
]

required_false = [
    "private_access_required",
    "network_required_after_clone",
    "media_or_model_payload_present",
    "admissibility_verdict_record_present",
    "terminal_closure_record_present",
    "release_candidate_ready",
    "issued",
    "media_present",
    "admissibility_verdict_present",
    "terminal_closure_present",
    "authority_satisfied",
    "may_advance_now",
]

for key in required_true:
    if obj.get(key) is not True:
        raise SystemExit(f"{key}=false")
for key in required_false:
    if obj.get(key) is not False:
        raise SystemExit(f"{key}=true")

if obj.get("outsider_replay_execution_result") != "PASS":
    raise SystemExit("OUTSIDER_REPLAY_EXECUTION_RESULT_NOT_PASS")
if obj.get("next_required_object") != "RELEASE_CANDIDATE_ADMISSIBILITY_VERDICT_RECORD":
    raise SystemExit("NEXT_REQUIRED_OBJECT_MISMATCH")

print("CINEMATICUM RELEASE CANDIDATE OUTSIDER REPLAY PASSAGE RECORD: PASS")
print(f"CURRENT_STATE={obj['current_state']}")
print(f"RELEASE_CANDIDATE_PLANNING_PERIMETER_COMPLETE={str(obj['release_candidate_planning_perimeter_complete']).lower()}")
print(f"ALL_REQUIRED_RELEASE_CANDIDATE_GAP_OBJECTS_PRESENT={str(obj['all_required_release_candidate_gap_objects_present']).lower()}")
print(f"RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD_PRESENT={str(obj['release_candidate_outsider_replay_execution_record_present']).lower()}")
print(f"OUTSIDER_REPLAY_EXECUTION_RECORD_PRESENT={str(obj['outsider_replay_execution_record_present']).lower()}")
print(f"OUTSIDER_REPLAY_EXECUTION_COMPLETED={str(obj['outsider_replay_execution_completed']).lower()}")
print(f"OUTSIDER_REPLAY_EXECUTION_RESULT={obj['outsider_replay_execution_result']}")
print(f"OUTSIDER_REPLAY_PASSAGE_RECORD_PRESENT={str(obj['outsider_replay_passage_record_present']).lower()}")
print(f"OUTSIDER_REPLAY_PASSAGE_DECLARED={str(obj['outsider_replay_passage_declared']).lower()}")
print(f"OUTSIDER_REPLAY_PASSED={str(obj['outsider_replay_passed']).lower()}")
print(f"ADMISSIBILITY_VERDICT_RECORD_PRESENT={str(obj['admissibility_verdict_record_present']).lower()}")
print(f"TERMINAL_CLOSURE_RECORD_PRESENT={str(obj['terminal_closure_record_present']).lower()}")
print(f"RELEASE_CANDIDATE_READY={str(obj['release_candidate_ready']).lower()}")
print(f"ISSUED={str(obj['issued']).lower()}")
print(f"MEDIA_PRESENT={str(obj['media_present']).lower()}")
print(f"ADMISSIBILITY_VERDICT_PRESENT={str(obj['admissibility_verdict_present']).lower()}")
print(f"TERMINAL_CLOSURE_PRESENT={str(obj['terminal_closure_present']).lower()}")
print(f"NEXT_REQUIRED_OBJECT={obj['next_required_object']}")
PY
