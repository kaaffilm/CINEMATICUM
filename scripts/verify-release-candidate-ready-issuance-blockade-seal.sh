#!/usr/bin/env bash
set -euo pipefail

python3 - <<'INNERPY'
import json
from pathlib import Path

p = Path("RELEASE_CANDIDATE_READY_ISSUANCE_BLOCKADE_SEAL.json")
assert p.exists(), "missing RELEASE_CANDIDATE_READY_ISSUANCE_BLOCKADE_SEAL.json"

o = json.loads(p.read_text(encoding="utf-8"))

assert o.get("object") == "RELEASE_CANDIDATE_READY_ISSUANCE_BLOCKADE_SEAL"
assert o.get("object_type") == "BLOCKADE_SEAL"
assert o.get("jurisdiction") == "CINEMATICUM"
assert o.get("case") == "CASE_001_THE_LAST_RENDER"
assert o.get("current_state") == "RELEASE_CANDIDATE_READY"
assert o.get("release_candidate_ready") is True
assert o.get("issuance_unblocked") is False
assert o.get("issued") is False
assert o.get("media_present") is False
assert o.get("valid_transition_attempt_present") is False
assert o.get("may_advance_now") is False
assert o.get("blockade_scope") == "RELEASE_CANDIDATE_READY_PRE_ISSUANCE_ONLY"
assert "implicit_issuance" in o.get("blocks", [])
assert "media_admission_without_valid_transition_attempt" in o.get("blocks", [])
assert o.get("next_required_object") == "RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_REQUEST"

print("CINEMATICUM RELEASE CANDIDATE READY ISSUANCE BLOCKADE SEAL: PASS")
print("CURRENT_STATE=RELEASE_CANDIDATE_READY")
print("RELEASE_CANDIDATE_READY=true")
print("VALID_TRANSITION_ATTEMPT_PRESENT=false")
print("MAY_ADVANCE_NOW=false")
print("ISSUANCE_UNBLOCKED=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("NEXT_REQUIRED_OBJECT=RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_REQUEST")
INNERPY
