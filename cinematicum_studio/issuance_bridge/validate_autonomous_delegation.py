from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_machine_mediated_authority import validate_machine_mediated_authority_ready

CASE_ROOT = Path("CASES")
AUTONOMOUS_DELEGATION_RECORD = "AUTONOMOUS_DELEGATION_READINESS_RECORD.json"


def validate_autonomous_delegation_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    machine_authority_ok, machine_authority_missing = validate_machine_mediated_authority_ready(case_id)
    if not machine_authority_ok:
        missing.append("MACHINE_MEDIATED_AUTHORITY_READY_REQUIRED_FOR_AUTONOMOUS_DELEGATION")
        missing.extend(f"MACHINE_MEDIATED_AUTHORITY::{item}" for item in machine_authority_missing)

    path = film_dir / AUTONOMOUS_DELEGATION_RECORD
    if not path.exists():
        missing.append(AUTONOMOUS_DELEGATION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("AUTONOMOUS_DELEGATION_READINESS_ACCEPTED")
        if record.get("autonomous_delegation_allowed") is not True:
            missing.append("AUTONOMOUS_DELEGATION_ALLOWED")
        if record.get("delegated_execution_allowed") is not True:
            missing.append("DELEGATED_EXECUTION_ALLOWED")
        if record.get("agentic_routing_allowed") is not True:
            missing.append("AGENTIC_ROUTING_ALLOWED")
        if record.get("automated_governance_action_allowed") is not True:
            missing.append("AUTOMATED_GOVERNANCE_ACTION_ALLOWED")
        if record.get("machine_initiated_publication_allowed") is not True:
            missing.append("MACHINE_INITIATED_PUBLICATION_ALLOWED")
        if record.get("autonomous_claim_propagation_allowed") is not True:
            missing.append("AUTONOMOUS_CLAIM_PROPAGATION_ALLOWED")
        if record.get("self_executing_authority_allowed") is not True:
            missing.append("SELF_EXECUTING_AUTHORITY_ALLOWED")

    return (len(missing) == 0, missing)
