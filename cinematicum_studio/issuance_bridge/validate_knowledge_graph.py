from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_canonical_citation import validate_canonical_citation_ready

CASE_ROOT = Path("CASES")
KNOWLEDGE_GRAPH_RECORD = "KNOWLEDGE_GRAPH_READINESS_RECORD.json"


def validate_knowledge_graph_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    citation_ok, citation_missing = validate_canonical_citation_ready(case_id)
    if not citation_ok:
        missing.append("CANONICAL_CITATION_READY_REQUIRED_FOR_KNOWLEDGE_GRAPH")
        missing.extend(f"CANONICAL_CITATION::{item}" for item in citation_missing)

    path = film_dir / KNOWLEDGE_GRAPH_RECORD
    if not path.exists():
        missing.append(KNOWLEDGE_GRAPH_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("KNOWLEDGE_GRAPH_READINESS_ACCEPTED")
        if record.get("knowledge_graph_allowed") is not True:
            missing.append("KNOWLEDGE_GRAPH_ALLOWED")
        if record.get("search_index_ingestion_allowed") is not True:
            missing.append("SEARCH_INDEX_INGESTION_ALLOWED")
        if record.get("metadata_graph_node_allowed") is not True:
            missing.append("METADATA_GRAPH_NODE_ALLOWED")
        if record.get("public_dataset_record_allowed") is not True:
            missing.append("PUBLIC_DATASET_RECORD_ALLOWED")
        if record.get("semantic_reference_allowed") is not True:
            missing.append("SEMANTIC_REFERENCE_ALLOWED")
        if record.get("linked_open_data_claim_allowed") is not True:
            missing.append("LINKED_OPEN_DATA_CLAIM_ALLOWED")
        if record.get("machine_readable_catalogue_allowed") is not True:
            missing.append("MACHINE_READABLE_CATALOGUE_ALLOWED")

    return (len(missing) == 0, missing)
