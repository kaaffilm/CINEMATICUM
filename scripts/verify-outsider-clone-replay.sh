#!/usr/bin/env bash
set -euo pipefail

PY="${PYTHON:-python3}"

"$PY" - <<\PYCODE
import json
from pathlib import Path

ROOT = Path.cwd()
record = json.loads((ROOT / "OUTSIDER_CLONE_REPLAY.json").read_text(encoding="utf-8"))

def require(key, expected):
    actual = record.get(key)
    assert actual == expected, {
        key: actual,
        "expected": expected,
        "issued": record.get("issued"),
        "issuance_type": record.get("issuance_type"),
        "protocol_perimeter_issued": record.get("protocol_perimeter_issued"),
        "protocol_film_issued": record.get("protocol_film_issued"),
        "admissible_motion_picture_issued": record.get("admissible_motion_picture_issued"),
        "motion_picture_issued": record.get("motion_picture_issued"),
        "motion_picture_media_issuance_ready": record.get("motion_picture_media_issuance_ready"),
        "media_present": record.get("media_present"),
    }

require("fresh_checkout_can_verify", True)
require("private_access_required", False)
require("network_required_after_clone", False)
require("media_or_model_payload_present", False)

require("issuance_type", "PROTOCOL_FILM")
require("protocol_perimeter_issued", True)
require("protocol_film_issued", True)

require("issued", False)
require("admissible_motion_picture_issued", False)
require("motion_picture_issued", False)
require("motion_picture_media_issuance_ready", False)
require("media_present", False)

print("CINEMATICUM OUTSIDER CLONE REPLAY: PASS")
for key in [
    "current_state",
    "active_current_state",
    "fresh_checkout_can_verify",
    "private_access_required",
    "network_required_after_clone",
    "media_or_model_payload_present",
    "protocol_perimeter_issued",
    "protocol_film_issued",
    "issuance_type",
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
