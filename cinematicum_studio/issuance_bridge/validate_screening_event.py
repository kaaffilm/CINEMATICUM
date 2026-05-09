from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_exhibition import validate_exhibition_ready

CASE_ROOT = Path("CASES")
SCREENING_EVENT_RECORD = "SCREENING_EVENT_READINESS_RECORD.json"


def validate_screening_event_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    exhibition_ok, exhibition_missing = validate_exhibition_ready(case_id)
    if not exhibition_ok:
        missing.append("EXHIBITION_READY_REQUIRED_FOR_SCREENING_EVENT")
        missing.extend(f"EXHIBITION::{item}" for item in exhibition_missing)

    path = film_dir / SCREENING_EVENT_RECORD
    if not path.exists():
        missing.append(SCREENING_EVENT_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("SCREENING_EVENT_READINESS_ACCEPTED")
        if record.get("screening_event_allowed") is not True:
            missing.append("SCREENING_EVENT_ALLOWED")
        if record.get("venue_schedule_allowed") is not True:
            missing.append("VENUE_SCHEDULE_ALLOWED")
        if record.get("ticketing_allowed") is not True:
            missing.append("TICKETING_ALLOWED")
        if record.get("audience_admission_allowed") is not True:
            missing.append("AUDIENCE_ADMISSION_ALLOWED")
        if record.get("premiere_event_allowed") is not True:
            missing.append("PREMIERE_EVENT_ALLOWED")

    return (len(missing) == 0, missing)
