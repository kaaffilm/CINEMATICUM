from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_observability import (
    validate_observability_ready,
)

CASE_ROOT = Path("CASES")
INCIDENT_RESPONSE_RECORD = "INCIDENT_RESPONSE_READINESS_RECORD.json"


def validate_incident_response_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    observability_ok, observability_missing = validate_observability_ready(case_id)
    if not observability_ok:
        missing.append("OBSERVABILITY_READY_REQUIRED_FOR_INCIDENT_RESPONSE")
        missing.extend(f"OBSERVABILITY::{item}" for item in observability_missing)

    path = film_dir / INCIDENT_RESPONSE_RECORD
    if not path.exists():
        missing.append(INCIDENT_RESPONSE_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("INCIDENT_RESPONSE_READINESS_ACCEPTED")
        if record.get("incident_response_allowed") is not True:
            missing.append("INCIDENT_RESPONSE_ALLOWED")
        if record.get("incident_declaration_allowed") is not True:
            missing.append("INCIDENT_DECLARATION_ALLOWED")
        if record.get("paging_allowed") is not True:
            missing.append("PAGING_ALLOWED")
        if record.get("escalation_allowed") is not True:
            missing.append("ESCALATION_ALLOWED")
        if record.get("incident_commander_assignment_allowed") is not True:
            missing.append("INCIDENT_COMMANDER_ASSIGNMENT_ALLOWED")
        if record.get("mitigation_action_allowed") is not True:
            missing.append("MITIGATION_ACTION_ALLOWED")
        if record.get("containment_action_allowed") is not True:
            missing.append("CONTAINMENT_ACTION_ALLOWED")
        if record.get("remediation_action_allowed") is not True:
            missing.append("REMEDIATION_ACTION_ALLOWED")
        if record.get("status_page_update_allowed") is not True:
            missing.append("STATUS_PAGE_UPDATE_ALLOWED")
        if record.get("customer_notification_allowed") is not True:
            missing.append("CUSTOMER_NOTIFICATION_ALLOWED")
        if record.get("postmortem_record_allowed") is not True:
            missing.append("POSTMORTEM_RECORD_ALLOWED")

    return (len(missing) == 0, missing)
