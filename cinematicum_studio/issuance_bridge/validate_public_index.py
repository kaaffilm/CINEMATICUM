from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_permanence import validate_permanence_ready

CASE_ROOT = Path("CASES")
PUBLIC_INDEX_RECORD = "CANONICAL_PUBLIC_INDEX_READINESS_RECORD.json"


def validate_public_index_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    permanence_ok, permanence_missing = validate_permanence_ready(case_id)
    if not permanence_ok:
        missing.append("PERMANENCE_READY_REQUIRED_FOR_PUBLIC_INDEX")
        missing.extend(f"PERMANENCE::{item}" for item in permanence_missing)

    path = film_dir / PUBLIC_INDEX_RECORD
    if not path.exists():
        missing.append(PUBLIC_INDEX_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("CANONICAL_PUBLIC_INDEX_READINESS_ACCEPTED")
        if record.get("canonical_public_index_allowed") is not True:
            missing.append("CANONICAL_PUBLIC_INDEX_ALLOWED")
        if record.get("public_discovery_record_allowed") is not True:
            missing.append("PUBLIC_DISCOVERY_RECORD_ALLOWED")
        if record.get("external_reference_allowed") is not True:
            missing.append("EXTERNAL_REFERENCE_ALLOWED")

    return (len(missing) == 0, missing)
