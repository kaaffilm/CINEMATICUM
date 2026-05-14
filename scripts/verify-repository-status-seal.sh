#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

seal_path = Path("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
seal = json.loads(seal_path.read_text())

def require(condition, message):
    if not condition:
        raise AssertionError(message)

require(seal["object_type"] == "CINEMATICUM_REPOSITORY_STATUS_SEAL", seal)
require(seal["schema_version"] == "cinematicum.repository_status_seal.v1", seal)
require(seal["surface_type"] == "REPOSITORY_STATUS_SEAL", seal)

require(seal["seal_is_current_truth_owner"] is False, seal)
require(seal["current_truth_owner"] == "CINEMATICUM_CURRENT_STATE_INDEX.json", seal)
require(seal["case_current_truth_owner"] == "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json", seal)
require(seal["current_state"] == "RELEASE_CANDIDATE_READY", seal)
require(seal["active_current_state"] == "RELEASE_CANDIDATE_READY", seal)
require(seal["release_candidate_ready"] is True, seal)

require(seal["protocol_issued"] is True, seal)
require(seal["protocol_film_issued"] is True, seal)
require(seal["protocol_perimeter_issued"] is True, seal)
require(seal["protocol_issued_object"] == "PUBLIC_REPLAYABLE_HASH_BOUND_PROTOCOL_PERIMETER", seal)

require(seal["issued"] is False, seal)
require(seal.get("issued_object") is None, seal)
require(seal["media_present"] is False, seal)
require(seal["motion_picture_media_issuance_ready"] is False, seal)
require(seal["admissible_motion_picture_issued"] is False, seal)
require(seal["motion_picture_issued"] is False, seal)

require(seal["raw_media_stored_in_git"] is False, seal)
require(seal["media_payload_present"] is False, seal)
require(seal["engine_present"] is False, seal)
require(seal["generation_present"] is False, seal)
require(seal["model_present"] is False, seal)
require(seal["model_weight_payload_present"] is False, seal)
require(seal["outsider_replay_passed"] is False, seal)
require(seal["admissibility_verdict_present"] is False, seal)
require(seal["terminal_closure_present"] is False, seal)

require(seal["private_access_required"] is False, seal)
require(seal["network_required_after_clone"] is False, seal)
require(seal["object_registry_fresh_required"] is True, seal)
require(seal["verify_all_pass_required"] is True, seal)


for forbidden in [
    "protocol film issuance means final-master media issuance without a media admission record",
    "the seal admits media without a hash-bound media admission record",
    "the seal creates an admissibility verdict",
    "the seal outranks current-state objects",
    "the seal proves outsider replay passed",
    "raw media is stored in git",
]:
    require(forbidden in seal["forbidden_readings"], seal)

print("CINEMATICUM REPOSITORY STATUS SEAL: PASS")
print(f"CURRENT_STATE={seal['current_state']}")
print(f"ISSUED={str(seal['issued']).lower()}")
print(f"ISSUED_OBJECT={seal['issued_object']}")
print(f"PROTOCOL_ISSUED={str(seal['protocol_issued']).lower()}")
print(f"PROTOCOL_ISSUED_OBJECT={seal['protocol_issued_object']}")
print(f"MEDIA_PRESENT={str(seal['media_present']).lower()}")
print(f"RAW_MEDIA_STORED_IN_GIT={str(seal['raw_media_stored_in_git']).lower()}")
print(f"MOTION_PICTURE_MEDIA_ISSUANCE_READY={str(seal['motion_picture_media_issuance_ready']).lower()}")
print(f"ADMISSIBLE_MOTION_PICTURE_ISSUED={str(seal['admissible_motion_picture_issued']).lower()}")
print(f"MOTION_PICTURE_ISSUED={str(seal['motion_picture_issued']).lower()}")
PY
