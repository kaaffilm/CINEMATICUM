#!/usr/bin/env bash
set -euo pipefail

PY="${PYTHON:-python3}"

"$PY" - <<'PYCODE'
import json
from pathlib import Path

ROOT = Path.cwd()
record = json.loads((ROOT / "OUTSIDER_CLONE_REPLAY.json").read_text(encoding="utf-8"))

def require_false(key):
    actual = record.get(key)
    assert actual is False, {
        "key": key,
        "actual": actual,
        "expected": False,
        "issued": record.get("issued"),
        "media_present": record.get("media_present"),
        "admissible_motion_picture_issued": record.get("admissible_motion_picture_issued"),
        "motion_picture_issued": record.get("motion_picture_issued"),
        "motion_picture_media_issuance_ready": record.get("motion_picture_media_issuance_ready"),
        "protocol_perimeter_issued": record.get("protocol_perimeter_issued"),
        "protocol_film_issued": record.get("protocol_film_issued"),
        "issuance_type": record.get("issuance_type"),
    }

def require_true(key):
    actual = record.get(key)
    assert actual is True, {"key": key, "actual": actual, "expected": True}

require_true("fresh_checkout_can_verify")
require_false("private_access_required")
require_false("network_required_after_clone")
require_false("media_or_model_payload_present")

require_false("issued")
require_false("media_present")
require_false("admissible_motion_picture_issued")
require_false("motion_picture_issued")
require_false("motion_picture_media_issuance_ready")

# Protocol flags may exist as historical/status fields, but may not create bare issuance.
if record.get("protocol_perimeter_issued") is True or record.get("protocol_film_issued") is True:
    assert record.get("issued") is False
    assert record.get("media_present") is False
    assert record.get("motion_picture_media_issuance_ready") is False

print("CINEMATICUM OUTSIDER CLONE REPLAY: PASS")
for key in [
    "current_state",
    "active_current_state",
    "fresh_checkout_can_verify",
    "private_access_required",
    "network_required_after_clone",
    "media_or_model_payload_present",
    "issuance_type",
    "protocol_perimeter_issued",
    "protocol_film_issued",
    "issued",
    "admissible_motion_picture_issued",
    "motion_picture_issued",
    "motion_picture_media_issuance_ready",
    "media_present",
]:
    value = record.get(key)
    if isinstance(value, bool):
        value = str(value).lower()
    print(f"{key.upper()}={value}")
PYCODE
