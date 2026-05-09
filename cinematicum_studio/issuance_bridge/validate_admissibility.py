from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_master import validate_master_ready
from cinematicum_studio.issuance_bridge.validate_acceptance import validate_cinematic_acceptance
from cinematicum_studio.issuance_bridge.validate_postproduction import validate_postproduction_acceptance


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


NON_ADMISSIBLE_RENDER_ARTIFACT_MARKERS = (
    "cinematicum-local-ffmpeg-stub",
    "local_video_generator",
    "stub",
    "mock",
    "placeholder",
    "proof",
    "synthetic",
)


def _take_ledger_declares_non_admissible_render_artifact(film_dir: Path) -> bool:
    ledger_path = film_dir / "TAKE_LEDGER.json"
    if not ledger_path.exists():
        return False

    ledger = _load_json(ledger_path)
    for shot in ledger.get("shots", []):
        for take in shot.get("takes", []):
            evidence = " ".join(
                str(take.get(key, "")).lower()
                for key in (
                    "backend",
                    "model",
                    "file_path",
                    "status",
                    "classification",
                    "artifact_type",
                    "generator",
                )
            )

            if any(marker in evidence for marker in NON_ADMISSIBLE_RENDER_ARTIFACT_MARKERS):
                return True

    return False

def _take_ledger_source_admissibility_unproven(film_dir: Path) -> bool:
    ledger_path = film_dir / "TAKE_LEDGER.json"
    if not ledger_path.exists():
        return False

    ledger = _load_json(ledger_path)
    for shot in ledger.get("shots", []):
        takes = shot.get("takes", [])
        if not takes:
            return True

        for take in takes:
            if take.get("is_admissible_film_source") is not True:
                return True
            if take.get("source_admissibility_classification") != "ADMISSIBLE_FINAL_FILM_SOURCE":
                return True

    return False

def _take_source_admissibility_evidence_missing(film_dir: Path) -> bool:
    ledger_path = film_dir / "TAKE_LEDGER.json"
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"

    if not ledger_path.exists():
        return False

    ledger = _load_json(ledger_path)
    admissible_takes = []
    for shot in ledger.get("shots", []):
        for take in shot.get("takes", []):
            if (
                take.get("is_admissible_film_source") is True
                and take.get("source_admissibility_classification") == "ADMISSIBLE_FINAL_FILM_SOURCE"
            ):
                admissible_takes.append(take)

    if not admissible_takes:
        return False

    if not evidence_path.exists():
        return True

    evidence = _load_json(evidence_path)
    records = {
        (record.get("take_id"), record.get("sha256"))
        for record in evidence.get("admissible_sources", [])
        if record.get("admissibility_evidence_accepted") is True
    }

    for take in admissible_takes:
        if (take.get("id"), take.get("sha256")) not in records:
            return True

    return False


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

    if _take_ledger_declares_non_admissible_render_artifact(film_dir):
        missing.append("NON_ADMISSIBLE_RENDER_ARTIFACT_NOT_FILM")

    if _take_ledger_source_admissibility_unproven(film_dir):
        missing.append("TAKE_LEDGER_SOURCE_ADMISSIBILITY_UNPROVEN")

    if _take_source_admissibility_evidence_missing(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_EVIDENCE_MISSING")

    proof_path = film_dir / "LOCAL_RENDER_PROOF_CLASSIFICATION.json"
    if not proof_path.exists():
        missing.append("LOCAL_RENDER_PROOF_CLASSIFICATION.json")
    else:
        proof = _load_json(proof_path)
        if proof.get("classification") == "LOCAL_RENDER_PROOF":
            missing.append("LOCAL_RENDER_PROOF_NOT_FILM")
        if proof.get("is_admissible_film") is True and proof.get("classification") == "LOCAL_RENDER_PROOF":
            missing.append("INVALID_PROOF_CLASSIFICATION_ADMITS_FILM")

    quality_path = film_dir / "CINEMATIC_QUALITY_ACCEPTANCE_RECORD.json"
    if not quality_path.exists():
        missing.append("CINEMATIC_QUALITY_ACCEPTANCE_RECORD.json")
    else:
        quality = _load_json(quality_path)
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
