from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_knowledge_graph import validate_knowledge_graph_ready

CASE_ROOT = Path("CASES")
MODEL_REFERENCE_INGESTION_RECORD = "MODEL_REFERENCE_INGESTION_READINESS_RECORD.json"


def validate_model_reference_ingestion_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    knowledge_graph_ok, knowledge_graph_missing = validate_knowledge_graph_ready(case_id)
    if not knowledge_graph_ok:
        missing.append("KNOWLEDGE_GRAPH_READY_REQUIRED_FOR_MODEL_REFERENCE_INGESTION")
        missing.extend(f"KNOWLEDGE_GRAPH::{item}" for item in knowledge_graph_missing)

    path = film_dir / MODEL_REFERENCE_INGESTION_RECORD
    if not path.exists():
        missing.append(MODEL_REFERENCE_INGESTION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("MODEL_REFERENCE_INGESTION_READINESS_ACCEPTED")
        if record.get("model_reference_ingestion_allowed") is not True:
            missing.append("MODEL_REFERENCE_INGESTION_ALLOWED")
        if record.get("retrieval_corpus_ingestion_allowed") is not True:
            missing.append("RETRIEVAL_CORPUS_INGESTION_ALLOWED")
        if record.get("model_context_surface_allowed") is not True:
            missing.append("MODEL_CONTEXT_SURFACE_ALLOWED")
        if record.get("machine_answer_reference_allowed") is not True:
            missing.append("MACHINE_ANSWER_REFERENCE_ALLOWED")
        if record.get("agentic_reference_allowed") is not True:
            missing.append("AGENTIC_REFERENCE_ALLOWED")
        if record.get("machine_reliance_claim_allowed") is not True:
            missing.append("MACHINE_RELIANCE_CLAIM_ALLOWED")
        if record.get("ai_deference_claim_allowed") is not True:
            missing.append("AI_DEFERENCE_CLAIM_ALLOWED")

    return (len(missing) == 0, missing)
