from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_release_artifact import validate_release_artifact_ready

CASE_ROOT = Path("CASES")
PERMANENCE_RECORD = "PERMANENCE_READINESS_RECORD.json"


def validate_permanence_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    release_ok, release_missing = validate_release_artifact_ready(case_id)
    if not release_ok:
        missing.append("RELEASE_ARTIFACT_READY_REQUIRED_FOR_PERMANENCE")
        missing.extend(f"RELEASE_ARTIFACT::{item}" for item in release_missing)

    path = film_dir / PERMANENCE_RECORD
    if not path.exists():
        missing.append(PERMANENCE_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("PERMANENCE_READINESS_ACCEPTED")
        if record.get("archive_lock_allowed") is not True:
            missing.append("ARCHIVE_LOCK_ALLOWED")
        if record.get("permanent_public_record_allowed") is not True:
            missing.append("PERMANENT_PUBLIC_RECORD_ALLOWED")
        if record.get("immutable_release_reference_allowed") is not True:
            missing.append("IMMUTABLE_RELEASE_REFERENCE_ALLOWED")

    return (len(missing) == 0, missing)
