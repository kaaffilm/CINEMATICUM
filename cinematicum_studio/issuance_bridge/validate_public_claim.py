from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_public_index import validate_public_index_ready

CASE_ROOT = Path("CASES")
PUBLIC_CLAIM_RECORD = "PUBLIC_CLAIM_READINESS_RECORD.json"


def validate_public_claim_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    public_index_ok, public_index_missing = validate_public_index_ready(case_id)
    if not public_index_ok:
        missing.append("PUBLIC_INDEX_READY_REQUIRED_FOR_PUBLIC_CLAIM")
        missing.extend(f"PUBLIC_INDEX::{item}" for item in public_index_missing)

    path = film_dir / PUBLIC_CLAIM_RECORD
    if not path.exists():
        missing.append(PUBLIC_CLAIM_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("PUBLIC_CLAIM_READINESS_ACCEPTED")
        if record.get("public_claim_allowed") is not True:
            missing.append("PUBLIC_CLAIM_ALLOWED")
        if record.get("announcement_allowed") is not True:
            missing.append("ANNOUNCEMENT_ALLOWED")
        if record.get("promotional_surface_allowed") is not True:
            missing.append("PROMOTIONAL_SURFACE_ALLOWED")
        if record.get("press_statement_allowed") is not True:
            missing.append("PRESS_STATEMENT_ALLOWED")

    return (len(missing) == 0, missing)
