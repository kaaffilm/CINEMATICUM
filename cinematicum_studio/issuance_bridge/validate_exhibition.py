from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_audience_surface import validate_audience_surface_ready

CASE_ROOT = Path("CASES")
EXHIBITION_RECORD = "EXHIBITION_READINESS_RECORD.json"


def validate_exhibition_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    audience_ok, audience_missing = validate_audience_surface_ready(case_id)
    if not audience_ok:
        missing.append("AUDIENCE_SURFACE_READY_REQUIRED_FOR_EXHIBITION")
        missing.extend(f"AUDIENCE_SURFACE::{item}" for item in audience_missing)

    path = film_dir / EXHIBITION_RECORD
    if not path.exists():
        missing.append(EXHIBITION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("EXHIBITION_READINESS_ACCEPTED")
        if record.get("exhibition_allowed") is not True:
            missing.append("EXHIBITION_ALLOWED")
        if record.get("public_screening_allowed") is not True:
            missing.append("PUBLIC_SCREENING_ALLOWED")
        if record.get("festival_submission_allowed") is not True:
            missing.append("FESTIVAL_SUBMISSION_ALLOWED")
        if record.get("theatrical_booking_allowed") is not True:
            missing.append("THEATRICAL_BOOKING_ALLOWED")
        if record.get("streaming_premiere_allowed") is not True:
            missing.append("STREAMING_PREMIERE_ALLOWED")

    return (len(missing) == 0, missing)
