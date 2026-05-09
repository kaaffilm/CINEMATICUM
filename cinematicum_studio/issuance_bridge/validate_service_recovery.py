from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_incident_response import (
    validate_incident_response_ready,
)

CASE_ROOT = Path("CASES")
SERVICE_RECOVERY_RECORD = "SERVICE_RECOVERY_READINESS_RECORD.json"


def validate_service_recovery_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    incident_ok, incident_missing = validate_incident_response_ready(case_id)
    if not incident_ok:
        missing.append("INCIDENT_RESPONSE_READY_REQUIRED_FOR_SERVICE_RECOVERY")
        missing.extend(f"INCIDENT_RESPONSE::{item}" for item in incident_missing)

    path = film_dir / SERVICE_RECOVERY_RECORD
    if not path.exists():
        missing.append(SERVICE_RECOVERY_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("SERVICE_RECOVERY_READINESS_ACCEPTED")
        if record.get("service_recovery_allowed") is not True:
            missing.append("SERVICE_RECOVERY_ALLOWED")
        if record.get("recovery_execution_allowed") is not True:
            missing.append("RECOVERY_EXECUTION_ALLOWED")
        if record.get("failover_allowed") is not True:
            missing.append("FAILOVER_ALLOWED")
        if record.get("traffic_restoration_allowed") is not True:
            missing.append("TRAFFIC_RESTORATION_ALLOWED")
        if record.get("rollback_completion_allowed") is not True:
            missing.append("ROLLBACK_COMPLETION_ALLOWED")
        if record.get("data_repair_allowed") is not True:
            missing.append("DATA_REPAIR_ALLOWED")
        if record.get("replay_execution_allowed") is not True:
            missing.append("REPLAY_EXECUTION_ALLOWED")
        if record.get("permanent_fix_claim_allowed") is not True:
            missing.append("PERMANENT_FIX_CLAIM_ALLOWED")
        if record.get("incident_closure_allowed") is not True:
            missing.append("INCIDENT_CLOSURE_ALLOWED")
        if record.get("resolved_status_claim_allowed") is not True:
            missing.append("RESOLVED_STATUS_CLAIM_ALLOWED")
        if record.get("customer_restoration_notice_allowed") is not True:
            missing.append("CUSTOMER_RESTORATION_NOTICE_ALLOWED")

    return (len(missing) == 0, missing)
