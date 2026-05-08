from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_issuance import validate_issuance_ready

CASE_ROOT = Path("CASES")
CURRENT_STATE_PATH = Path("CURRENT_PRODUCTION_STATE.json")

PUBLIC_TERMINAL_STATES = {
    "ISSUED",
    "RELEASED",
    "PUBLISHED",
}


def _current_state() -> str | None:
    if not CURRENT_STATE_PATH.exists():
        return None

    data = json.loads(CURRENT_STATE_PATH.read_text())

    if not isinstance(data, dict):
        return None

    preferred_keys = (
        "active_current_state",
        "current_state",
        "current_production_state",
        "production_state",
        "state",
    )

    for key in preferred_keys:
        value = data.get(key)
        if isinstance(value, str):
            return value

    for key, value in data.items():
        if "state" in key.lower() and isinstance(value, str):
            return value

    return None


def validate_publication_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    issuance_ok, issuance_missing = validate_issuance_ready(case_id)
    if not issuance_ok:
        missing.append("ISSUANCE_READY_REQUIRED_FOR_PUBLICATION")
        missing.extend(f"ISSUANCE::{item}" for item in issuance_missing)

    state = _current_state()
    if state not in PUBLIC_TERMINAL_STATES:
        missing.append("TERMINAL_STATE_REQUIRED_FOR_PUBLICATION")
        if state is None:
            missing.append("CURRENT_PRODUCTION_STATE_UNREADABLE")
        else:
            missing.append(f"CURRENT_STATE::{state}")

    publication_path = film_dir / "PUBLICATION_READINESS_RECORD.json"
    if not publication_path.exists():
        missing.append("PUBLICATION_READINESS_RECORD.json")
    else:
        publication = json.loads(publication_path.read_text())
        if publication.get("accepted") is not True:
            missing.append("PUBLICATION_READINESS_ACCEPTED")

    return (len(missing) == 0, missing)
