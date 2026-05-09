from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_audience_reception import validate_audience_reception_ready

CASE_ROOT = Path("CASES")
AWARD_ELIGIBILITY_RECORD = "AWARD_ELIGIBILITY_READINESS_RECORD.json"


def validate_award_eligibility_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    reception_ok, reception_missing = validate_audience_reception_ready(case_id)
    if not reception_ok:
        missing.append("AUDIENCE_RECEPTION_READY_REQUIRED_FOR_AWARD_ELIGIBILITY")
        missing.extend(f"AUDIENCE_RECEPTION::{item}" for item in reception_missing)

    path = film_dir / AWARD_ELIGIBILITY_RECORD
    if not path.exists():
        missing.append(AWARD_ELIGIBILITY_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("AWARD_ELIGIBILITY_READINESS_ACCEPTED")
        if record.get("award_submission_allowed") is not True:
            missing.append("AWARD_SUBMISSION_ALLOWED")
        if record.get("festival_award_claim_allowed") is not True:
            missing.append("FESTIVAL_AWARD_CLAIM_ALLOWED")
        if record.get("jury_prize_claim_allowed") is not True:
            missing.append("JURY_PRIZE_CLAIM_ALLOWED")
        if record.get("critic_award_claim_allowed") is not True:
            missing.append("CRITIC_AWARD_CLAIM_ALLOWED")
        if record.get("audience_award_claim_allowed") is not True:
            missing.append("AUDIENCE_AWARD_CLAIM_ALLOWED")
        if record.get("official_selection_claim_allowed") is not True:
            missing.append("OFFICIAL_SELECTION_CLAIM_ALLOWED")

    return (len(missing) == 0, missing)
