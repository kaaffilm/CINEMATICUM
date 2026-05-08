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

KNOWN_NON_TERMINAL_STATES = {
    "RELEASE_CANDIDATE_READY",
    "MASTER_READY",
    "MEDIA_PRESENT",
    "PRODUCTION_READY",
    "IN_PRODUCTION",
    "BOOTSTRAPPED",
    "DRAFT",
}

KNOWN_PRODUCTION_STATES = PUBLIC_TERMINAL_STATES | KNOWN_NON_TERMINAL_STATES

STATE_IDENTITY_VALUES = {
    "CURRENT_PRODUCTION_STATE",
}


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def _current_state() -> str | None:
    if not CURRENT_STATE_PATH.exists():
        return None

    data = json.loads(CURRENT_STATE_PATH.read_text())

    preferred_keys = (
        "active_current_state",
        "current_state",
        "current_production_state",
        "production_state",
        "active_state",
        "state",
    )

    if isinstance(data, dict):
        for key in preferred_keys:
            value = data.get(key)
            if isinstance(value, str) and value not in STATE_IDENTITY_VALUES:
                return value

    for value in _walk_strings(data):
        if value in KNOWN_PRODUCTION_STATES:
            return value

    for value in _walk_strings(data):
        if value not in STATE_IDENTITY_VALUES and (
            value.endswith("_READY")
            or value in PUBLIC_TERMINAL_STATES
        ):
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
