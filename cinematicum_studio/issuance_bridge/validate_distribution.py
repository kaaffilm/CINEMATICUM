from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_publication import validate_publication_ready

CASE_ROOT = Path("CASES")
DISTRIBUTION_RECORD = "DISTRIBUTION_READINESS_RECORD.json"


def validate_distribution_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    publication_ok, publication_missing = validate_publication_ready(case_id)
    if not publication_ok:
        missing.append("PUBLICATION_READY_REQUIRED_FOR_DISTRIBUTION")
        missing.extend(f"PUBLICATION::{item}" for item in publication_missing)

    path = film_dir / DISTRIBUTION_RECORD
    if not path.exists():
        missing.append(DISTRIBUTION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("DISTRIBUTION_READINESS_ACCEPTED")
        if record.get("public_export_allowed") is not True:
            missing.append("PUBLIC_EXPORT_ALLOWED")

    return (len(missing) == 0, missing)
