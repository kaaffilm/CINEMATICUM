from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_credential_custody import validate_credential_custody_ready

CASE_ROOT = Path("CASES")
EXECUTION_PROVENANCE_RECORD = "EXECUTION_PROVENANCE_READINESS_RECORD.json"


def validate_execution_provenance_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    custody_ok, custody_missing = validate_credential_custody_ready(case_id)
    if not custody_ok:
        missing.append("CREDENTIAL_CUSTODY_READY_REQUIRED_FOR_EXECUTION_PROVENANCE")
        missing.extend(f"CREDENTIAL_CUSTODY::{item}" for item in custody_missing)

    path = film_dir / EXECUTION_PROVENANCE_RECORD
    if not path.exists():
        missing.append(EXECUTION_PROVENANCE_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("EXECUTION_PROVENANCE_READINESS_ACCEPTED")
        if record.get("execution_provenance_allowed") is not True:
            missing.append("EXECUTION_PROVENANCE_ALLOWED")
        if record.get("signed_execution_receipt_allowed") is not True:
            missing.append("SIGNED_EXECUTION_RECEIPT_ALLOWED")
        if record.get("tamper_evident_audit_log_allowed") is not True:
            missing.append("TAMPER_EVIDENT_AUDIT_LOG_ALLOWED")
        if record.get("custody_chain_attestation_allowed") is not True:
            missing.append("CUSTODY_CHAIN_ATTESTATION_ALLOWED")
        if record.get("replay_resistant_operation_record_allowed") is not True:
            missing.append("REPLAY_RESISTANT_OPERATION_RECORD_ALLOWED")
        if record.get("nonrepudiation_claim_allowed") is not True:
            missing.append("NONREPUDIATION_CLAIM_ALLOWED")
        if record.get("compliance_evidence_export_allowed") is not True:
            missing.append("COMPLIANCE_EVIDENCE_EXPORT_ALLOWED")
        if record.get("incident_reconstruction_allowed") is not True:
            missing.append("INCIDENT_RECONSTRUCTION_ALLOWED")

    return (len(missing) == 0, missing)
