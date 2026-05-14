#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY2'
import json
from pathlib import Path
index = json.loads(Path("CINEMATICUM_CURRENT_STATE_INDEX.json").read_text())
assert index["active_current_state"] == "ISSUED_ADMISSIBLE_MOTION_PICTURE", index["active_current_state"]
assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == "ISSUED_ADMISSIBLE_MOTION_PICTURE"
assert index["issued"] is True
assert index["issued_object"] == "ADMISSIBLE_MOTION_PICTURE"
assert index["media_present"] is False
assert index["raw_media_stored_in_git"] is False
print("CINEMATICUM CURRENT STATE INDEX: PASS")
print("CASE_001=THE_LAST_RENDER")
print("ACTIVE_CURRENT_STATE=ISSUED_ADMISSIBLE_MOTION_PICTURE")
print("ISSUED=true")
print("ISSUED_OBJECT=ADMISSIBLE_MOTION_PICTURE")
print("MEDIA_PRESENT=false")
print("RAW_MEDIA_STORED_IN_GIT=false")
print("ONE_ACTIVE_CASE_STATE=true")
PY2
