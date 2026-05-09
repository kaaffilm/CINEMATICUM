from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_award_eligibility import validate_award_eligibility_ready

CASE_ROOT = Path("CASES")
INSTITUTIONAL_RECOGNITION_RECORD = "INSTITUTIONAL_RECOGNITION_READINESS_RECORD.json"


def validate_institutional_recognition_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    award_ok, award_missing = validate_award_eligibility_ready(case_id)
    if not award_ok:
        missing.append("AWARD_ELIGIBILITY_READY_REQUIRED_FOR_INSTITUTIONAL_RECOGNITION")
        missing.extend(f"AWARD_ELIGIBILITY::{item}" for item in award_missing)

    path = film_dir / INSTITUTIONAL_RECOGNITION_RECORD
    if not path.exists():
        missing.append(INSTITUTIONAL_RECOGNITION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("INSTITUTIONAL_RECOGNITION_READINESS_ACCEPTED")
        if record.get("institutional_recognition_allowed") is not True:
            missing.append("INSTITUTIONAL_RECOGNITION_ALLOWED")
        if record.get("canon_listing_allowed") is not True:
            missing.append("CANON_LISTING_ALLOWED")
        if record.get("catalogue_claim_allowed") is not True:
            missing.append("CATALOGUE_CLAIM_ALLOWED")
        if record.get("retrospective_programming_allowed") is not True:
            missing.append("RETROSPECTIVE_PROGRAMMING_ALLOWED")
        if record.get("curatorial_selection_claim_allowed") is not True:
            missing.append("CURATORIAL_SELECTION_CLAIM_ALLOWED")
        if record.get("cultural_significance_claim_allowed") is not True:
            missing.append("CULTURAL_SIGNIFICANCE_CLAIM_ALLOWED")

    return (len(missing) == 0, missing)
