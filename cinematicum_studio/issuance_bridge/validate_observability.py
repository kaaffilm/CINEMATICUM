from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_runtime_operation import (
    validate_runtime_operation_ready,
)

CASE_ROOT = Path("CASES")
OBSERVABILITY_RECORD = "OBSERVABILITY_READINESS_RECORD.json"


def validate_observability_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    runtime_ok, runtime_missing = validate_runtime_operation_ready(case_id)
    if not runtime_ok:
        missing.append("RUNTIME_OPERATION_READY_REQUIRED_FOR_OBSERVABILITY")
        missing.extend(f"RUNTIME_OPERATION::{item}" for item in runtime_missing)

    path = film_dir / OBSERVABILITY_RECORD
    if not path.exists():
        missing.append(OBSERVABILITY_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("OBSERVABILITY_READINESS_ACCEPTED")
        if record.get("observability_allowed") is not True:
            missing.append("OBSERVABILITY_ALLOWED")
        if record.get("health_status_claim_allowed") is not True:
            missing.append("HEALTH_STATUS_CLAIM_ALLOWED")
        if record.get("telemetry_interpretation_allowed") is not True:
            missing.append("TELEMETRY_INTERPRETATION_ALLOWED")
        if record.get("alert_evaluation_allowed") is not True:
            missing.append("ALERT_EVALUATION_ALLOWED")
        if record.get("slo_evaluation_allowed") is not True:
            missing.append("SLO_EVALUATION_ALLOWED")
        if record.get("incident_signal_allowed") is not True:
            missing.append("INCIDENT_SIGNAL_ALLOWED")
        if record.get("dashboard_publication_allowed") is not True:
            missing.append("DASHBOARD_PUBLICATION_ALLOWED")
        if record.get("log_correlation_allowed") is not True:
            missing.append("LOG_CORRELATION_ALLOWED")
        if record.get("metric_export_allowed") is not True:
            missing.append("METRIC_EXPORT_ALLOWED")
        if record.get("trace_analysis_allowed") is not True:
            missing.append("TRACE_ANALYSIS_ALLOWED")

    return (len(missing) == 0, missing)
