#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

seal = json.loads(Path("CINEMATICUM_REPOSITORY_STATUS_SEAL.json").read_text(encoding="utf-8"))

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def b(value):
    return "true" if bool(value) else "false"

require(seal.get("object_type") == "CINEMATICUM_REPOSITORY_STATUS_SEAL", seal)
require(seal.get("schema_version") == "cinematicum.repository_status_seal.v1", seal)
require(seal.get("case_id") == "CASE_001_THE_LAST_RENDER", seal)

require(seal.get("current_state") == "RELEASE_CANDIDATE_READY", seal)
require(seal.get("active_current_state") == "RELEASE_CANDIDATE_READY", seal)
require(seal.get("release_candidate_ready") is True, seal)

# Protocol-perimeter issuance is allowed.
require(seal.get("issuance_type") == "PROTOCOL_FILM", seal)
require(seal.get("protocol_issued") is True, seal)
require(seal.get("protocol_perimeter_issued") is True, seal)
require(seal.get("protocol_film_issued") is True, seal)
require(seal.get("issued_object") == "PUBLIC_REPLAYABLE_HASH_BOUND_PROTOCOL_PERIMETER", seal)

# Bare/final motion-picture issuance is forbidden without media.
require(seal.get("issued") is False, seal)
require(seal.get("admissible_motion_picture_issued") is False, seal)
require(seal.get("motion_picture_issued") is False, seal)
require(seal.get("motion_picture_media_issuance_ready") is False, seal)

require(seal.get("media_present") is False, seal)
require(seal.get("media_payload_present") is False, seal)
require(seal.get("engine_present") is False, seal)
require(seal.get("generation_present") is False, seal)
require(seal.get("model_present") is False, seal)
require(seal.get("model_weight_payload_present") is False, seal)

require(seal.get("private_access_required") is False, seal)
require(seal.get("network_required_after_clone") is False, seal)
require(seal.get("object_registry_fresh_required") is True, seal)
require(seal.get("verify_all_pass_required") is True, seal)

print("CINEMATICUM REPOSITORY STATUS SEAL: PASS")
print(f"ACTIVE_CURRENT_STATE={seal.get('active_current_state')}")
print(f"RELEASE_CANDIDATE_READY={b(seal.get('release_candidate_ready'))}")
print(f"ISSUANCE_TYPE={seal.get('issuance_type')}")
print(f"PROTOCOL_ISSUED={b(seal.get('protocol_issued'))}")
print(f"PROTOCOL_PERIMETER_ISSUED={b(seal.get('protocol_perimeter_issued'))}")
print(f"PROTOCOL_FILM_ISSUED={b(seal.get('protocol_film_issued'))}")
print(f"ISSUED={b(seal.get('issued'))}")
print(f"ADMISSIBLE_MOTION_PICTURE_ISSUED={b(seal.get('admissible_motion_picture_issued'))}")
print(f"MOTION_PICTURE_ISSUED={b(seal.get('motion_picture_issued'))}")
print(f"MOTION_PICTURE_MEDIA_ISSUANCE_READY={b(seal.get('motion_picture_media_issuance_ready'))}")
print(f"MEDIA_PRESENT={b(seal.get('media_present'))}")
print(f"OBJECT_REGISTRY_FRESH_REQUIRED={b(seal.get('object_registry_fresh_required'))}")
PY
