#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY2'
import json
from pathlib import Path
seal = json.loads(Path("CINEMATICUM_REPOSITORY_STATUS_SEAL.json").read_text())
assert seal["current_state"] == "ISSUED_ADMISSIBLE_MOTION_PICTURE", seal["current_state"]
assert seal["issued"] is True
assert seal["issued_object"] == "ADMISSIBLE_MOTION_PICTURE"
assert seal["media_present"] is False
assert seal["raw_media_stored_in_git"] is False
print("CINEMATICUM REPOSITORY STATUS SEAL: PASS")
print("CURRENT_STATE=ISSUED_ADMISSIBLE_MOTION_PICTURE")
print("ISSUED=true")
print("ISSUED_OBJECT=ADMISSIBLE_MOTION_PICTURE")
print("MEDIA_PRESENT=false")
print("RAW_MEDIA_STORED_IN_GIT=false")
PY2
