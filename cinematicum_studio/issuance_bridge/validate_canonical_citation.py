from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_institutional_recognition import validate_institutional_recognition_ready

CASE_ROOT = Path("CASES")
CANONICAL_CITATION_RECORD = "CANONICAL_CITATION_READINESS_RECORD.json"


def validate_canonical_citation_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    recognition_ok, recognition_missing = validate_institutional_recognition_ready(case_id)
    if not recognition_ok:
        missing.append("INSTITUTIONAL_RECOGNITION_READY_REQUIRED_FOR_CANONICAL_CITATION")
        missing.extend(f"INSTITUTIONAL_RECOGNITION::{item}" for item in recognition_missing)

    path = film_dir / CANONICAL_CITATION_RECORD
    if not path.exists():
        missing.append(CANONICAL_CITATION_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("CANONICAL_CITATION_READINESS_ACCEPTED")
        if record.get("canonical_citation_allowed") is not True:
            missing.append("CANONICAL_CITATION_ALLOWED")
        if record.get("scholarly_reference_allowed") is not True:
            missing.append("SCHOLARLY_REFERENCE_ALLOWED")
        if record.get("archive_reference_allowed") is not True:
            missing.append("ARCHIVE_REFERENCE_ALLOWED")
        if record.get("catalogue_reference_allowed") is not True:
            missing.append("CATALOGUE_REFERENCE_ALLOWED")
        if record.get("institutional_footnote_allowed") is not True:
            missing.append("INSTITUTIONAL_FOOTNOTE_ALLOWED")
        if record.get("external_metadata_reference_allowed") is not True:
            missing.append("EXTERNAL_METADATA_REFERENCE_ALLOWED")

    return (len(missing) == 0, missing)
