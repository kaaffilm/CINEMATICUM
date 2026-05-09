from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_screening_event import validate_screening_event_ready

CASE_ROOT = Path("CASES")
AUDIENCE_ATTENDANCE_RECORD = "AUDIENCE_ATTENDANCE_READINESS_RECORD.json"


def validate_audience_attendance_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    screening_ok, screening_missing = validate_screening_event_ready(case_id)
    if not screening_ok:
        missing.append("SCREENING_EVENT_READY_REQUIRED_FOR_AUDIENCE_ATTENDANCE")
        missing.extend(f"SCREENING_EVENT::{item}" for item in screening_missing)

    path = film_dir / AUDIENCE_ATTENDANCE_RECORD
    if not path.exists():
        missing.append(AUDIENCE_ATTENDANCE_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("AUDIENCE_ATTENDANCE_READINESS_ACCEPTED")
        if record.get("attendance_record_allowed") is not True:
            missing.append("ATTENDANCE_RECORD_ALLOWED")
        if record.get("box_office_record_allowed") is not True:
            missing.append("BOX_OFFICE_RECORD_ALLOWED")
        if record.get("audience_count_allowed") is not True:
            missing.append("AUDIENCE_COUNT_ALLOWED")
        if record.get("q_and_a_record_allowed") is not True:
            missing.append("Q_AND_A_RECORD_ALLOWED")
        if record.get("premiere_presence_record_allowed") is not True:
            missing.append("PREMIERE_PRESENCE_RECORD_ALLOWED")

    return (len(missing) == 0, missing)
