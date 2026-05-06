#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

OLD = 'OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED'
TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
paths = [
    'CASES/CASE_001_THE_LAST_RENDER/CURRENT_STATE_INDEX_ADVANCEMENT_RECORD/CURRENT_STATE_INDEX_ADVANCEMENT_RECORD.json',
    'CASES/CASE_001_THE_LAST_RENDER/CURRENT_STATE_INDEX_ADVANCEMENT_RECORD_STATUS.json',
    'CINEMATICUM_CURRENT_STATE_INDEX_ADVANCEMENT_RECORD_LAW.json',
]
objs = [json.loads(Path(p).read_text()) for p in paths]
for obj in objs:
    assert obj['from_state'] == OLD
    assert obj['to_state'] == TARGET
    assert obj['release_candidate_ready'] is False
    assert obj['issued'] is False
    assert obj['media_present'] is False
    assert obj['outsider_replay_passed'] is False
    assert obj['admissibility_verdict_present'] is False
    assert obj['terminal_closure_present'] is False
record = objs[0]
assert record['accepted_authority_object_count'] == 8
assert record['instantiated_authority_object_count'] == 8
assert record['unfilled_authority_object_slot_count'] == 0
assert record['next_required_object'] == 'RELEASE_CANDIDATE_GAP_LEDGER'
print('CINEMATICUM CURRENT STATE INDEX ADVANCEMENT RECORD: PASS')
print(f'FROM_STATE={OLD}')
print(f'TO_STATE={TARGET}')
print('RELEASE_CANDIDATE_READY=false')
print('ISSUED=false')
print('MEDIA_PRESENT=false')
print('NEXT_REQUIRED_OBJECT=RELEASE_CANDIDATE_GAP_LEDGER')
PY2
