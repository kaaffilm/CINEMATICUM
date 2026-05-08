#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest tests/test_release_candidate_ready_issuance_unblocking_execution_record.py

python3 - <<'PY'
import json
from pathlib import Path

r = json.loads(Path("RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_EXECUTION_RECORD.json").read_text())

print("CINEMATICUM RELEASE CANDIDATE READY ISSUANCE UNBLOCKING EXECUTION RECORD: PASS")
print(f"CURRENT_STATE={r['current_state']}")
print(f"EXECUTION_SCOPE={r['execution_scope']}")
print(f"EXECUTION_OBJECT={r['execution_object']}")
print(f"EXECUTION_ID={r['execution_id']}")
print(f"PRIOR_DECISION_OBJECT={r['prior_decision_object']}")
print(f"PRIOR_DECISION_ID={r['prior_decision_id']}")
print(f"REQUEST_OBJECT={r['request_object']}")
print(f"REQUEST_ID={r['request_id']}")
print(f"REQUESTED_NEXT_STATE={r['requested_next_state']}")
print(f"RELEASE_CANDIDATE_READY={str(r['release_candidate_ready']).lower()}")
print(f"BLOCKADE_SEAL_PRESENT={str(r['blockade_seal_present']).lower()}")
print(f"ISSUANCE_UNBLOCKING_REQUEST_PRESENT={str(r['issuance_unblocking_request_present']).lower()}")
print(f"ISSUANCE_UNBLOCKING_DECISION_RECORD_PRESENT={str(r['issuance_unblocking_decision_record_present']).lower()}")
print(f"DECISION_ACCEPTS_REQUEST={str(r['decision_accepts_request']).lower()}")
print(f"DECISION_AUTHORIZES_ISSUANCE_UNBLOCKING={str(r['decision_authorizes_issuance_unblocking']).lower()}")
print(f"ISSUANCE_UNBLOCKING_EXECUTION_AUTHORIZED={str(r['issuance_unblocking_execution_authorized']).lower()}")
print(f"ISSUANCE_UNBLOCKING_EXECUTED={str(r['issuance_unblocking_executed']).lower()}")
print(f"ISSUANCE_UNBLOCKED={str(r['issuance_unblocked']).lower()}")
print(f"ISSUED={str(r['issued']).lower()}")
print(f"MEDIA_PRESENT={str(r['media_present']).lower()}")
print(f"MAY_ADVANCE_NOW={str(r['may_advance_now']).lower()}")
print(f"NEXT_REQUIRED_OBJECT={r['next_required_object']}")
PY
