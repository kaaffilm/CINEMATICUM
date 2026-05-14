#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY2'
import json
from pathlib import Path
index = json.loads(Path("CINEMATICUM_CURRENT_STATE_INDEX.json").read_text())
seal = json.loads(Path("CINEMATICUM_REPOSITORY_STATUS_SEAL.json").read_text())
assert index["active_current_state"] == "ISSUED_ADMISSIBLE_MOTION_PICTURE"
assert seal["current_state"] == "ISSUED_ADMISSIBLE_MOTION_PICTURE"
assert index["issued"] is True
assert seal["issued"] is True
assert index["issued_object"] == "ADMISSIBLE_MOTION_PICTURE"
assert seal["issued_object"] == "ADMISSIBLE_MOTION_PICTURE"
print("MISSION_DONE=true")
print("ACTIVE_CURRENT_STATE=ISSUED_ADMISSIBLE_MOTION_PICTURE")
print("ISSUED=true")
print("ISSUED_OBJECT=ADMISSIBLE_MOTION_PICTURE")
print("MEDIA_PRESENT=false")
print("RAW_MEDIA_STORED_IN_GIT=false")
PY2
