from __future__ import annotations

from cinematicum_studio.issuance_bridge.validate_admissibility import (
    validate_admissible_motion_picture,
)
from cinematicum_studio.issuance_bridge.validate_master import validate_master_ready


def validate_issuance_ready(case_id: str) -> tuple[bool, list[str]]:
    missing: list[str] = []

    master_ok, master_missing = validate_master_ready(case_id)
    if not master_ok:
        missing.extend(f"MASTER::{item}" for item in master_missing)

    admissible_ok, admissible_missing = validate_admissible_motion_picture(case_id)
    if not admissible_ok:
        missing.extend(f"ADMISSIBILITY::{item}" for item in admissible_missing)

    return (len(missing) == 0, missing)
