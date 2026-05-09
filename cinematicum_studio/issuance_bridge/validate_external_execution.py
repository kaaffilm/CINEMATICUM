from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_autonomous_delegation import validate_autonomous_delegation_ready

CASE_ROOT = Path("CASES")
EXTERNAL_EXECUTION_RECORD = "EXTERNAL_EXECUTION_READINESS_RECORD.json"


def validate_external_execution_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    autonomous_ok, autonomous_missing = validate_autonomous_delegation_ready(case_id)
    if not autonomous_ok:
        missing.append("AUTONOMOUS_DELEGATION_READY_REQUIRED_FOR_EXTERNAL_EXECUTION")
        missing.extend(f"AUTONOMOUS_DELEGATION::{item}" for item in autonomous_missing)

    path = film_dir / EXTERNAL_EXECUTION_RECORD
    if not path.exists():
        missing.append(EXTERNAL_EXECUTION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("EXTERNAL_EXECUTION_READINESS_ACCEPTED")
        if record.get("external_execution_allowed") is not True:
            missing.append("EXTERNAL_EXECUTION_ALLOWED")
        if record.get("repository_mutation_allowed") is not True:
            missing.append("REPOSITORY_MUTATION_ALLOWED")
        if record.get("infrastructure_mutation_allowed") is not True:
            missing.append("INFRASTRUCTURE_MUTATION_ALLOWED")
        if record.get("third_party_api_execution_allowed") is not True:
            missing.append("THIRD_PARTY_API_EXECUTION_ALLOWED")
        if record.get("operational_command_dispatch_allowed") is not True:
            missing.append("OPERATIONAL_COMMAND_DISPATCH_ALLOWED")
        if record.get("legal_financial_instruction_allowed") is not True:
            missing.append("LEGAL_FINANCIAL_INSTRUCTION_ALLOWED")
        if record.get("external_system_side_effect_allowed") is not True:
            missing.append("EXTERNAL_SYSTEM_SIDE_EFFECT_ALLOWED")
        if record.get("irreversible_world_action_allowed") is not True:
            missing.append("IRREVERSIBLE_WORLD_ACTION_ALLOWED")

    return (len(missing) == 0, missing)
