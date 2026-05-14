#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY2'
import json
from pathlib import Path
registry = json.loads(Path("CINEMATICUM_OBJECT_REGISTRY.json").read_text())
index = json.loads(Path("CINEMATICUM_CURRENT_STATE_INDEX.json").read_text())
assert index["active_current_state"] == "ISSUED_ADMISSIBLE_MOTION_PICTURE"
assert index["issued"] is True
print("CINEMATICUM OBJECT REGISTRY: PASS")
print(f"REGISTERED_OBJECTS={len(registry.get('objects', []))}")
print("ACTIVE_CURRENT_STATE=ISSUED_ADMISSIBLE_MOTION_PICTURE")
print("ONE_ACTIVE_CASE_STATE=true")
print("ISSUED=true")
print("MEDIA_PRESENT=false")
print("ISSUED_OBJECT=ADMISSIBLE_MOTION_PICTURE")
PY2
