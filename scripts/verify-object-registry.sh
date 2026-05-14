#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

registry = json.loads(Path("CINEMATICUM_OBJECT_REGISTRY.json").read_text())
index = json.loads(Path("CINEMATICUM_CURRENT_STATE_INDEX.json").read_text())

assert registry.get("current_active_state") == "RELEASE_CANDIDATE_READY", registry.get("current_active_state")
assert registry.get("active_current_state") == "RELEASE_CANDIDATE_READY", registry.get("active_current_state")
assert registry.get("issued") is False, registry.get("issued")
assert registry.get("media_present") is False, registry.get("media_present")
assert registry.get("issued_object") is None, registry.get("issued_object")
assert index.get("active_current_state") == "RELEASE_CANDIDATE_READY"

print("CINEMATICUM OBJECT REGISTRY: PASS")
print(f"REGISTERED_OBJECTS={len(registry.get('objects', []))}")
print("ACTIVE_CURRENT_STATE=RELEASE_CANDIDATE_READY")
print("ONE_ACTIVE_CASE_STATE=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("ISSUED_OBJECT=None")
PY
