#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PY:-python3}"
if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
fi

"$PYTHON" - <<'PY'
import json
from pathlib import Path

ROOT = Path.cwd()

def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")

case_id = "CASE_001_THE_LAST_RENDER"
active = index["active_case_states"][case_id]

assert seal["surface_type"] == "REPOSITORY_STATUS_SEAL"
assert seal["case_id"] == case_id
assert seal["current_state"] == active
assert seal["current_state"] == "RELEASE_CANDIDATE_READY"
assert index["active_current_state"] == "RELEASE_CANDIDATE_READY"
assert index["active_case_states"][case_id] == "RELEASE_CANDIDATE_READY"

assert seal["release_candidate_ready"] is True

# Protocol-film issuance is true.
assert seal["issued"] is True
assert seal["issuance_type"] == "PROTOCOL_FILM"
assert seal["protocol_perimeter_issued"] is True
assert seal["protocol_film_issued"] is True
assert seal["issued_object"] == "PUBLIC_REPLAYABLE_HASH_BOUND_PROTOCOL_PERIMETER"

# Final-master / media issuance remains false.
assert seal["motion_picture_media_issuance_ready"] is False
assert seal["media_present"] is False
assert seal["media_payload_present"] is False
assert seal["model_weight_payload_present"] is False
assert seal["private_access_required"] is False
assert seal["network_required_after_clone"] is False
assert seal["outsider_replay_passed"] is False

print("CINEMATICUM REPOSITORY STATUS SEAL: PASS")
print(f"ACTIVE_CURRENT_STATE={seal['current_state']}")
print(f"RELEASE_CANDIDATE_READY={str(seal['release_candidate_ready']).lower()}")
print(f"ISSUED={str(seal['issued']).lower()}")
print(f"ISSUANCE_TYPE={seal['issuance_type']}")
print(f"PROTOCOL_PERIMETER_ISSUED={str(seal['protocol_perimeter_issued']).lower()}")
print(f"PROTOCOL_FILM_ISSUED={str(seal['protocol_film_issued']).lower()}")
print(f"MOTION_PICTURE_MEDIA_ISSUANCE_READY={str(seal['motion_picture_media_issuance_ready']).lower()}")
print(f"MEDIA_PRESENT={str(seal['media_present']).lower()}")
print(f"OUTSIDER_REPLAY_PASSED={str(seal['outsider_replay_passed']).lower()}")
print("VERIFY_ALL_REQUIRED=true")
print("REGISTRY_FRESH_REQUIRED=true")
PY
