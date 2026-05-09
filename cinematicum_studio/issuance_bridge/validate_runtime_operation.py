from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_deployment_authorization import (
    validate_deployment_authorization_ready,
)

CASE_ROOT = Path("CASES")
RUNTIME_OPERATION_RECORD = "RUNTIME_OPERATION_READINESS_RECORD.json"


def validate_runtime_operation_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    deployment_ok, deployment_missing = validate_deployment_authorization_ready(case_id)
    if not deployment_ok:
        missing.append("DEPLOYMENT_AUTHORIZATION_READY_REQUIRED_FOR_RUNTIME_OPERATION")
        missing.extend(f"DEPLOYMENT_AUTHORIZATION::{item}" for item in deployment_missing)

    path = film_dir / RUNTIME_OPERATION_RECORD
    if not path.exists():
        missing.append(RUNTIME_OPERATION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("RUNTIME_OPERATION_READINESS_ACCEPTED")
        if record.get("runtime_operation_allowed") is not True:
            missing.append("RUNTIME_OPERATION_ALLOWED")
        if record.get("production_runtime_activation_allowed") is not True:
            missing.append("PRODUCTION_RUNTIME_ACTIVATION_ALLOWED")
        if record.get("live_traffic_exposure_allowed") is not True:
            missing.append("LIVE_TRAFFIC_EXPOSURE_ALLOWED")
        if record.get("service_account_activation_allowed") is not True:
            missing.append("SERVICE_ACCOUNT_ACTIVATION_ALLOWED")
        if record.get("scheduler_activation_allowed") is not True:
            missing.append("SCHEDULER_ACTIVATION_ALLOWED")
        if record.get("telemetry_emission_allowed") is not True:
            missing.append("TELEMETRY_EMISSION_ALLOWED")
        if record.get("alert_routing_allowed") is not True:
            missing.append("ALERT_ROUTING_ALLOWED")
        if record.get("operational_rollback_allowed") is not True:
            missing.append("OPERATIONAL_ROLLBACK_ALLOWED")
        if record.get("external_invocation_allowed") is not True:
            missing.append("EXTERNAL_INVOCATION_ALLOWED")

    return (len(missing) == 0, missing)
