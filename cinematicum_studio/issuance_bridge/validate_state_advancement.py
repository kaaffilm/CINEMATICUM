from __future__ import annotations

from cinematicum_studio.issuance_bridge.validate_issuance import validate_issuance_ready


ISSUANCE_REQUIRED_TARGET_STATES = {
    "ISSUED",
    "RELEASED",
    "PUBLISHED",
    "PUBLICLY_RELEASED",
    "PUBLICATION_READY",
    "DISTRIBUTION_READY",
}

ISSUANCE_REQUIRED_TOKEN = "ISSUANCE_READY_REQUIRED_FOR_STATE_ADVANCEMENT"


def validate_state_advancement(case_id: str, target_state: str) -> tuple[bool, list[str]]:
    normalized_target = target_state.strip().upper()
    missing: list[str] = []

    if normalized_target in ISSUANCE_REQUIRED_TARGET_STATES:
        issuance_ok, issuance_missing = validate_issuance_ready(case_id)
        if not issuance_ok:
            missing.append(ISSUANCE_REQUIRED_TOKEN)
            missing.extend(f"ISSUANCE::{item}" for item in issuance_missing)

    return (len(missing) == 0, missing)
