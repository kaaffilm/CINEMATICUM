from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_distribution import validate_distribution_ready

CASE_ROOT = Path("CASES")
RELEASE_ARTIFACT_RECORD = "RELEASE_ARTIFACT_READINESS_RECORD.json"


def validate_release_artifact_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    distribution_ok, distribution_missing = validate_distribution_ready(case_id)
    if not distribution_ok:
        missing.append("DISTRIBUTION_READY_REQUIRED_FOR_RELEASE_ARTIFACT")
        missing.extend(f"DISTRIBUTION::{item}" for item in distribution_missing)

    path = film_dir / RELEASE_ARTIFACT_RECORD
    if not path.exists():
        missing.append(RELEASE_ARTIFACT_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("RELEASE_ARTIFACT_READINESS_ACCEPTED")
        if record.get("release_artifact_allowed") is not True:
            missing.append("RELEASE_ARTIFACT_ALLOWED")
        if record.get("external_package_allowed") is not True:
            missing.append("EXTERNAL_PACKAGE_ALLOWED")

    return (len(missing) == 0, missing)
