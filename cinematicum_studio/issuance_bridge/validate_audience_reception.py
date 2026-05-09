from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_audience_attendance import validate_audience_attendance_ready

CASE_ROOT = Path("CASES")
AUDIENCE_RECEPTION_RECORD = "AUDIENCE_RECEPTION_READINESS_RECORD.json"


def validate_audience_reception_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    attendance_ok, attendance_missing = validate_audience_attendance_ready(case_id)
    if not attendance_ok:
        missing.append("AUDIENCE_ATTENDANCE_READY_REQUIRED_FOR_RECEPTION")
        missing.extend(f"AUDIENCE_ATTENDANCE::{item}" for item in attendance_missing)

    path = film_dir / AUDIENCE_RECEPTION_RECORD
    if not path.exists():
        missing.append(AUDIENCE_RECEPTION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("AUDIENCE_RECEPTION_READINESS_ACCEPTED")
        if record.get("review_record_allowed") is not True:
            missing.append("REVIEW_RECORD_ALLOWED")
        if record.get("critic_response_allowed") is not True:
            missing.append("CRITIC_RESPONSE_ALLOWED")
        if record.get("audience_response_allowed") is not True:
            missing.append("AUDIENCE_RESPONSE_ALLOWED")
        if record.get("rating_record_allowed") is not True:
            missing.append("RATING_RECORD_ALLOWED")
        if record.get("laurel_claim_allowed") is not True:
            missing.append("LAUREL_CLAIM_ALLOWED")
        if record.get("reception_claim_allowed") is not True:
            missing.append("RECEPTION_CLAIM_ALLOWED")

    return (len(missing) == 0, missing)
