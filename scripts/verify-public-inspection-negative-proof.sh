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

proof = load(find_object("PUBLIC_INSPECTION_NEGATIVE_PROOF"))

def require(condition, label):
    if condition is not True:
        raise AssertionError(label)

def b(value):
    return "true" if bool(value) else "false"

require(proof.get("issued") is False, "issued")
require(proof.get("admissible_motion_picture_issued", False) is False, "admissible_motion_picture_issued")
require(proof.get("motion_picture_issued", False) is False, "motion_picture_issued")
require(proof.get("motion_picture_media_issuance_ready", False) is False, "motion_picture_media_issuance_ready")
require(proof.get("media_present") is False, "media_present")
require(proof.get("media_payload_present", False) is False, "media_payload_present")
require(proof.get("replay_passed", proof.get("outsider_replay_passed", False)) is False, "replay_passed")
require(proof.get("public_inspection_verdict_present", False) is False, "public_inspection_verdict_present")
require(proof.get("admissibility_verdict_present", False) is False, "admissibility_verdict_present")
require(proof.get("terminal_closure_present", False) is False, "terminal_closure_present")

print("CINEMATICUM PUBLIC INSPECTION NEGATIVE PROOF: PASS")
print(f"ISSUED={b(proof.get('issued'))}")
print(f"ADMISSIBLE_MOTION_PICTURE_ISSUED={b(proof.get('admissible_motion_picture_issued'))}")
print(f"MOTION_PICTURE_ISSUED={b(proof.get('motion_picture_issued'))}")
print(f"MOTION_PICTURE_MEDIA_ISSUANCE_READY={b(proof.get('motion_picture_media_issuance_ready'))}")
print(f"MEDIA_PRESENT={b(proof.get('media_present'))}")
print(f"REPLAY_PASSED={b(proof.get('replay_passed', proof.get('outsider_replay_passed', False)))}")
print(f"VERDICT_PRESENT={b(proof.get('public_inspection_verdict_present', False) or proof.get('admissibility_verdict_present', False))}")
print(f"TERMINAL_CLOSURE={b(proof.get('terminal_closure_present'))}")
INNERPY
