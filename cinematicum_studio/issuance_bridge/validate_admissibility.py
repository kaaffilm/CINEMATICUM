from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_master import validate_master_ready
from cinematicum_studio.issuance_bridge.validate_acceptance import validate_cinematic_acceptance
from cinematicum_studio.issuance_bridge.validate_postproduction import validate_postproduction_acceptance


def validate_admissible_motion_picture(case_id: str) -> tuple[bool, list[str]]:
    """
    Hard distinction:
    - validate_master_ready proves media/timeline/master presence.
    - this validator proves film admissibility.
    A local proof render must never satisfy film admissibility by itself.
    """
    missing: list[str] = []

    master_ok, master_missing = validate_master_ready(case_id)
    if not master_ok:
        missing.extend([f"MASTER::{item}" for item in master_missing])

    film_dir = Path("CASES") / case_id / "FILM"

    proof_path = film_dir / "LOCAL_RENDER_PROOF_CLASSIFICATION.json"
    if proof_path.exists():
        proof = json.loads(proof_path.read_text())
        if proof.get("classification") == "LOCAL_RENDER_PROOF":
            missing.append("LOCAL_RENDER_PROOF_NOT_FILM")
        if proof.get("is_admissible_film") is True:
            missing.append("INVALID_PROOF_CLASSIFICATION_ADMITS_FILM")

    quality_path = film_dir / "CINEMATIC_QUALITY_ACCEPTANCE_RECORD.json"
    if not quality_path.exists():
        missing.append("CINEMATIC_QUALITY_ACCEPTANCE_RECORD.json")
    else:
        quality = json.loads(quality_path.read_text())
        if quality.get("accepted") is not True:
            missing.append("CINEMATIC_QUALITY_ACCEPTED")
        if quality.get("classification") == "LOCAL_RENDER_PROOF":
            missing.append("PROOF_RENDER_REJECTED_BY_CINEMATIC_QUALITY_GATE")

    acceptance_ok, acceptance_missing = validate_cinematic_acceptance(case_id)
    if not acceptance_ok:
        missing.extend(f"ACCEPTANCE::{item}" for item in acceptance_missing)

    post_ok, post_missing = validate_postproduction_acceptance(case_id)
    if not post_ok:
        missing.extend(f"POSTPRODUCTION::{item}" for item in post_missing)

    return (len(missing) == 0, missing)
