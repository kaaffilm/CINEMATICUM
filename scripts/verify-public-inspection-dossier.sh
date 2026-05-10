#!/usr/bin/env bash
set -euo pipefail

python3 - <<'INNERPY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def find_object(token):
    direct = [
        Path(token + ".json"),
        Path("CINEMATICUM_" + token + ".json"),
    ]
    for path in direct:
        if path.exists():
            return path
    for path in Path(".").rglob("*.json"):
        if ".git" in path.parts:
            continue
        try:
            data = load(path)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        text = " ".join(str(data.get(k, "")) for k in ("object_type", "surface_type", "schema_version"))
        if token in text or token in path.name:
            return path
    raise AssertionError(token + " not found")

dossier = load(find_object("PUBLIC_INSPECTION_DOSSIER"))

def require(condition, label):
    if condition is not True:
        raise AssertionError(label)

def b(value):
    return "true" if bool(value) else "false"

require(dossier.get("private_access_required") is False, "private_access_required")
require(dossier.get("issued") is False, "issued")
require(dossier.get("admissible_motion_picture_issued", False) is False, "admissible_motion_picture_issued")
require(dossier.get("motion_picture_issued", False) is False, "motion_picture_issued")
require(dossier.get("motion_picture_media_issuance_ready", False) is False, "motion_picture_media_issuance_ready")
require(dossier.get("media_present") is False, "media_present")
require(dossier.get("media_payload_present", False) is False, "media_payload_present")
require(dossier.get("replay_passed", dossier.get("outsider_replay_passed", False)) is False, "replay_passed")

print("CINEMATICUM PUBLIC INSPECTION DOSSIER: PASS")
print(f"PRIVATE_ACCESS_REQUIRED={b(dossier.get('private_access_required'))}")
print(f"ACTIVE_CURRENT_STATE={dossier.get('active_current_state')}")
print(f"ISSUED={b(dossier.get('issued'))}")
print(f"ADMISSIBLE_MOTION_PICTURE_ISSUED={b(dossier.get('admissible_motion_picture_issued'))}")
print(f"MOTION_PICTURE_ISSUED={b(dossier.get('motion_picture_issued'))}")
print(f"MOTION_PICTURE_MEDIA_ISSUANCE_READY={b(dossier.get('motion_picture_media_issuance_ready'))}")
print(f"MEDIA_PRESENT={b(dossier.get('media_present'))}")
print(f"REPLAY_PASSED={b(dossier.get('replay_passed', dossier.get('outsider_replay_passed', False)))}")
INNERPY
