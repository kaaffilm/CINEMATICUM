from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_public_claim import validate_public_claim_ready

CASE_ROOT = Path("CASES")
AUDIENCE_SURFACE_RECORD = "AUDIENCE_SURFACE_READINESS_RECORD.json"


def validate_audience_surface_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    public_claim_ok, public_claim_missing = validate_public_claim_ready(case_id)
    if not public_claim_ok:
        missing.append("PUBLIC_CLAIM_READY_REQUIRED_FOR_AUDIENCE_SURFACE")
        missing.extend(f"PUBLIC_CLAIM::{item}" for item in public_claim_missing)

    path = film_dir / AUDIENCE_SURFACE_RECORD
    if not path.exists():
        missing.append(AUDIENCE_SURFACE_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("AUDIENCE_SURFACE_READINESS_ACCEPTED")
        if record.get("audience_surface_allowed") is not True:
            missing.append("AUDIENCE_SURFACE_ALLOWED")
        if record.get("website_listing_allowed") is not True:
            missing.append("WEBSITE_LISTING_ALLOWED")
        if record.get("trailer_page_allowed") is not True:
            missing.append("TRAILER_PAGE_ALLOWED")
        if record.get("press_kit_allowed") is not True:
            missing.append("PRESS_KIT_ALLOWED")
        if record.get("social_publication_allowed") is not True:
            missing.append("SOCIAL_PUBLICATION_ALLOWED")

    return (len(missing) == 0, missing)
