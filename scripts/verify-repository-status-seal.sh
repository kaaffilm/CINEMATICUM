#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY2'
import json
from pathlib import Path

seal = json.loads(Path("CINEMATICUM_REPOSITORY_STATUS_SEAL.json").read_text())

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

require(seal["issued"] is False, seal)
require(seal.get("issued_object") is None, seal)
require(seal["media_present"] is False, seal)
require(seal["media_substance_passed"] is False, seal)
require(seal["blocked_by"] == "MEDIA_SUBSTANCE_GATE", seal)
require(seal["mission_done"] is False, seal)

for key in (
    "motion_picture_media_issuance_ready",
    "admissible_motion_picture_issued",
    "motion_picture_issued",
    "motion_picture_media_issued",
    "final_master_media_issued",
    "protocol_issued",
    "protocol_film_issued",
    "protocol_perimeter_issued",
):
    require(seal.get(key) is False, f"{key}={seal.get(key)!r}")

require(seal["raw_media_stored_in_git"] is False, seal)
require(seal["media_payload_present"] is False, seal)
require(seal["engine_present"] is False, seal)
require(seal["generation_present"] is False, seal)
require(seal["model_present"] is False, seal)
require(seal["model_weight_payload_present"] is False, seal)
require(seal["outsider_replay_passed"] is True, seal)
require(seal["admissibility_verdict_present"] is True, seal)
require(seal["terminal_closure_present"] is True, seal)
require(seal["private_access_required"] is True, seal)
require(seal["network_required_after_clone"] is False, seal)
require(seal["object_registry_fresh_required"] is True, seal)

require(seal["media_sha256"] == "1822a3c1f7a1718fbd38e6ecabb74f9f0abff6369553051569cdd4178971f5a8", seal)
require(seal["media_bytes"] == 831197, seal)
require(seal["media_mime"] == "video/mp4", seal)
require(seal["media_name"] == "THE_LAST_RENDER_v001.mp4", seal)
require(seal["media_uri"] == "local-quarantine://CASE_001_THE_LAST_RENDER/renders/THE_LAST_RENDER_v001.mp4", seal)

print("CINEMATICUM REPOSITORY STATUS SEAL: PASS")
print(f"CURRENT_STATE={seal['current_state']}")
print(f"ISSUED={str(seal['issued']).lower()}")
print(f"ISSUED_OBJECT={seal.get('issued_object')}")
print(f"PROTOCOL_ISSUED={str(seal.get('protocol_issued', False)).lower()}")
print(f"PROTOCOL_ISSUED_OBJECT={seal.get('protocol_issued_object')}")
print(f"MEDIA_PRESENT={str(seal['media_present']).lower()}")
print(f"MEDIA_SUBSTANCE_PASSED={str(seal['media_substance_passed']).lower()}")
print(f"BLOCKED_BY={seal['blocked_by']}")
print(f"RAW_MEDIA_STORED_IN_GIT={str(seal['raw_media_stored_in_git']).lower()}")
PY2
