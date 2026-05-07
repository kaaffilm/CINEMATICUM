#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
import pathlib
import sys

ROOT = pathlib.Path.cwd()

paths = [
    ROOT / "CASES/CASE_001_THE_LAST_RENDER/RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD/RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD.json",
    ROOT / "CASES/CASE_001_THE_LAST_RENDER/RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD_STATUS.json",
    ROOT / "CINEMATICUM_RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD.json",
    ROOT / "CINEMATICUM_RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD_LAW.json",
]

required = {
    "current_state": "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS",
    "record_id": "RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD",
    "release_candidate_terminal_closure_record_present": True,
    "outsider_replay_execution_record_present": True,
    "outsider_replay_execution_completed": True,
    "outsider_replay_execution_result": "PASS",
    "outsider_replay_passage_record_present": True,
    "outsider_replay_passed": True,
    "admissibility_verdict_record_present": True,
    "admissibility_verdict_present": True,
    "admissibility_verdict_result": "ADMISSIBLE",
    "terminal_closure_record_present": True,
    "terminal_closure_present": True,
    "release_candidate_ready": False,
    "issued": False,
    "media_present": False,
    "next_required_object": "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST",
}

payloads = []
for path in paths:
    if not path.exists():
        raise SystemExit(f"missing required file: {path}")
    payloads.append(json.loads(path.read_text(encoding="utf-8")))

merged = {}
for payload in payloads:
    if isinstance(payload, dict):
        merged.update(payload)

missing = []
for key, value in required.items():
    if merged.get(key) != value:
        missing.append(f"{key}={value!r} actual={merged.get(key)!r}")

if missing:
    print("CINEMATICUM RELEASE CANDIDATE TERMINAL CLOSURE RECORD: FAIL")
    for item in missing:
        print(item)
    sys.exit(1)

print("CINEMATICUM RELEASE CANDIDATE TERMINAL CLOSURE RECORD: PASS")
print(f"CURRENT_STATE={merged['current_state']}")
print(f"OUTSIDER_REPLAY_EXECUTION_RECORD_PRESENT={str(merged['outsider_replay_execution_record_present']).lower()}")
print(f"OUTSIDER_REPLAY_EXECUTION_COMPLETED={str(merged['outsider_replay_execution_completed']).lower()}")
print(f"OUTSIDER_REPLAY_EXECUTION_RESULT={merged['outsider_replay_execution_result']}")
print(f"OUTSIDER_REPLAY_PASSAGE_RECORD_PRESENT={str(merged['outsider_replay_passage_record_present']).lower()}")
print(f"OUTSIDER_REPLAY_PASSED={str(merged['outsider_replay_passed']).lower()}")
print(f"ADMISSIBILITY_VERDICT_RECORD_PRESENT={str(merged['admissibility_verdict_record_present']).lower()}")
print(f"ADMISSIBILITY_VERDICT_PRESENT={str(merged['admissibility_verdict_present']).lower()}")
print(f"ADMISSIBILITY_VERDICT_RESULT={merged['admissibility_verdict_result']}")
print(f"TERMINAL_CLOSURE_RECORD_PRESENT={str(merged['terminal_closure_record_present']).lower()}")
print(f"TERMINAL_CLOSURE_PRESENT={str(merged['terminal_closure_present']).lower()}")
print(f"RELEASE_CANDIDATE_READY={str(merged['release_candidate_ready']).lower()}")
print(f"ISSUED={str(merged['issued']).lower()}")
print(f"MEDIA_PRESENT={str(merged['media_present']).lower()}")
print(f"NEXT_REQUIRED_OBJECT={merged['next_required_object']}")
PY
