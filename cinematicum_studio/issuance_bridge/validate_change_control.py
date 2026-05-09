from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_execution_provenance import validate_execution_provenance_ready

CASE_ROOT = Path("CASES")
CHANGE_CONTROL_RECORD = "CHANGE_CONTROL_READINESS_RECORD.json"


def validate_change_control_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    provenance_ok, provenance_missing = validate_execution_provenance_ready(case_id)
    if not provenance_ok:
        missing.append("EXECUTION_PROVENANCE_READY_REQUIRED_FOR_CHANGE_CONTROL")
        missing.extend(f"EXECUTION_PROVENANCE::{item}" for item in provenance_missing)

    path = film_dir / CHANGE_CONTROL_RECORD
    if not path.exists():
        missing.append(CHANGE_CONTROL_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("CHANGE_CONTROL_READINESS_ACCEPTED")
        if record.get("change_control_allowed") is not True:
            missing.append("CHANGE_CONTROL_ALLOWED")
        if record.get("approved_change_request_allowed") is not True:
            missing.append("APPROVED_CHANGE_REQUEST_ALLOWED")
        if record.get("independent_review_allowed") is not True:
            missing.append("INDEPENDENT_REVIEW_ALLOWED")
        if record.get("separation_of_duties_allowed") is not True:
            missing.append("SEPARATION_OF_DUTIES_ALLOWED")
        if record.get("rollback_plan_allowed") is not True:
            missing.append("ROLLBACK_PLAN_ALLOWED")
        if record.get("blast_radius_assessment_allowed") is not True:
            missing.append("BLAST_RADIUS_ASSESSMENT_ALLOWED")
        if record.get("emergency_change_override_allowed") is not True:
            missing.append("EMERGENCY_CHANGE_OVERRIDE_ALLOWED")
        if record.get("post_execution_attestation_allowed") is not True:
            missing.append("POST_EXECUTION_ATTESTATION_ALLOWED")

    return (len(missing) == 0, missing)
