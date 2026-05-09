from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_model_reference_ingestion import validate_model_reference_ingestion_ready

CASE_ROOT = Path("CASES")
MACHINE_MEDIATED_AUTHORITY_RECORD = "MACHINE_MEDIATED_AUTHORITY_READINESS_RECORD.json"


def validate_machine_mediated_authority_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    model_ingestion_ok, model_ingestion_missing = validate_model_reference_ingestion_ready(case_id)
    if not model_ingestion_ok:
        missing.append("MODEL_REFERENCE_INGESTION_READY_REQUIRED_FOR_MACHINE_MEDIATED_AUTHORITY")
        missing.extend(f"MODEL_REFERENCE_INGESTION::{item}" for item in model_ingestion_missing)

    path = film_dir / MACHINE_MEDIATED_AUTHORITY_RECORD
    if not path.exists():
        missing.append(MACHINE_MEDIATED_AUTHORITY_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("MACHINE_MEDIATED_AUTHORITY_READINESS_ACCEPTED")
        if record.get("machine_mediated_authority_allowed") is not True:
            missing.append("MACHINE_MEDIATED_AUTHORITY_ALLOWED")
        if record.get("generated_summary_allowed") is not True:
            missing.append("GENERATED_SUMMARY_ALLOWED")
        if record.get("model_answer_claim_allowed") is not True:
            missing.append("MODEL_ANSWER_CLAIM_ALLOWED")
        if record.get("agentic_public_action_allowed") is not True:
            missing.append("AGENTIC_PUBLIC_ACTION_ALLOWED")
        if record.get("automated_recommendation_allowed") is not True:
            missing.append("AUTOMATED_RECOMMENDATION_ALLOWED")
        if record.get("synthetic_citation_claim_allowed") is not True:
            missing.append("SYNTHETIC_CITATION_CLAIM_ALLOWED")
        if record.get("ai_endorsement_claim_allowed") is not True:
            missing.append("AI_ENDORSEMENT_CLAIM_ALLOWED")

    return (len(missing) == 0, missing)
