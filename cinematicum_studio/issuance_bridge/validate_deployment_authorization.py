from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_change_control import validate_change_control_ready

CASE_ROOT = Path("CASES")
DEPLOYMENT_AUTHORIZATION_RECORD = "DEPLOYMENT_AUTHORIZATION_READINESS_RECORD.json"


def validate_deployment_authorization_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    change_ok, change_missing = validate_change_control_ready(case_id)
    if not change_ok:
        missing.append("CHANGE_CONTROL_READY_REQUIRED_FOR_DEPLOYMENT_AUTHORIZATION")
        missing.extend(f"CHANGE_CONTROL::{item}" for item in change_missing)

    path = film_dir / DEPLOYMENT_AUTHORIZATION_RECORD
    if not path.exists():
        missing.append(DEPLOYMENT_AUTHORIZATION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("DEPLOYMENT_AUTHORIZATION_READINESS_ACCEPTED")
        if record.get("deployment_authorization_allowed") is not True:
            missing.append("DEPLOYMENT_AUTHORIZATION_ALLOWED")
        if record.get("release_promotion_allowed") is not True:
            missing.append("RELEASE_PROMOTION_ALLOWED")
        if record.get("production_deployment_allowed") is not True:
            missing.append("PRODUCTION_DEPLOYMENT_ALLOWED")
        if record.get("environment_targeting_allowed") is not True:
            missing.append("ENVIRONMENT_TARGETING_ALLOWED")
        if record.get("deployment_window_allowed") is not True:
            missing.append("DEPLOYMENT_WINDOW_ALLOWED")
        if record.get("operator_assignment_allowed") is not True:
            missing.append("OPERATOR_ASSIGNMENT_ALLOWED")
        if record.get("deployment_lock_release_allowed") is not True:
            missing.append("DEPLOYMENT_LOCK_RELEASE_ALLOWED")
        if record.get("rollback_execution_allowed") is not True:
            missing.append("ROLLBACK_EXECUTION_ALLOWED")

    return (len(missing) == 0, missing)
