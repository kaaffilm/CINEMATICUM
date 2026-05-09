from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_service_recovery import (
    validate_service_recovery_ready,
)

CASE_ROOT = Path("CASES")
RECOVERY_VERIFICATION_RECORD = "RECOVERY_VERIFICATION_READINESS_RECORD.json"


def validate_recovery_verification_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    service_recovery_ok, service_recovery_missing = validate_service_recovery_ready(case_id)
    if not service_recovery_ok:
        missing.append("SERVICE_RECOVERY_READY_REQUIRED_FOR_RECOVERY_VERIFICATION")
        missing.extend(f"SERVICE_RECOVERY::{item}" for item in service_recovery_missing)

    path = film_dir / RECOVERY_VERIFICATION_RECORD
    if not path.exists():
        missing.append(RECOVERY_VERIFICATION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("RECOVERY_VERIFICATION_READINESS_ACCEPTED")
        if record.get("recovery_verification_allowed") is not True:
            missing.append("RECOVERY_VERIFICATION_ALLOWED")
        if record.get("post_recovery_health_verification_allowed") is not True:
            missing.append("POST_RECOVERY_HEALTH_VERIFICATION_ALLOWED")
        if record.get("traffic_stability_verification_allowed") is not True:
            missing.append("TRAFFIC_STABILITY_VERIFICATION_ALLOWED")
        if record.get("data_integrity_verification_allowed") is not True:
            missing.append("DATA_INTEGRITY_VERIFICATION_ALLOWED")
        if record.get("rollback_verification_allowed") is not True:
            missing.append("ROLLBACK_VERIFICATION_ALLOWED")
        if record.get("replay_completeness_verification_allowed") is not True:
            missing.append("REPLAY_COMPLETENESS_VERIFICATION_ALLOWED")
        if record.get("customer_impact_end_claim_allowed") is not True:
            missing.append("CUSTOMER_IMPACT_END_CLAIM_ALLOWED")
        if record.get("monitoring_stability_claim_allowed") is not True:
            missing.append("MONITORING_STABILITY_CLAIM_ALLOWED")
        if record.get("normal_operations_restored_claim_allowed") is not True:
            missing.append("NORMAL_OPERATIONS_RESTORED_CLAIM_ALLOWED")
        if record.get("incident_deescalation_allowed") is not True:
            missing.append("INCIDENT_DEESCALATION_ALLOWED")
        if record.get("recovery_success_claim_allowed") is not True:
            missing.append("RECOVERY_SUCCESS_CLAIM_ALLOWED")

    return (len(missing) == 0, missing)
