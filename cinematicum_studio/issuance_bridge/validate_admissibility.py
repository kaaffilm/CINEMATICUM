from __future__ import annotations

import hashlib
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



def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _take_source_admissibility_evidence_payload_invalid(film_dir: Path) -> bool:
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    if not evidence_path.exists():
        return False

    evidence = _load_json(evidence_path)
    for record in evidence.get("admissible_sources", []):
        if record.get("admissibility_evidence_accepted") is not True:
            continue

        payload = record.get("evidence_file_path")
        expected_sha256 = record.get("evidence_sha256")

        if not payload or not expected_sha256:
            return True

        payload_path = Path(payload)
        if not payload_path.exists():
            return True

        try:
            payload_path.relative_to(film_dir)
        except ValueError:
            return True

        if _sha256_path(payload_path) != expected_sha256:
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



def _take_source_admissibility_evidence_payload_unbound(film_dir: Path) -> bool:
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    if not evidence_path.exists():
        return False

    evidence = _load_json(evidence_path)
    for record in evidence.get("admissible_sources", []):
        if record.get("admissibility_evidence_accepted") is not True:
            continue

        payload = record.get("evidence_file_path")
        expected_sha256 = record.get("evidence_sha256")
        if not payload or not expected_sha256:
            continue

        payload_path = Path(payload)
        if not payload_path.exists():
            continue

        try:
            payload_path.relative_to(film_dir)
        except ValueError:
            continue

        if _sha256_path(payload_path) != expected_sha256:
            continue

        try:
            payload_record = _load_json(payload_path)
        except json.JSONDecodeError:
            return True

        if payload_record.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_EVIDENCE":
            return True
        if payload_record.get("case_id") != evidence.get("case_id"):
            return True
        if payload_record.get("take_id") != record.get("take_id"):
            return True
        if payload_record.get("source_sha256") != record.get("sha256"):
            return True
        if payload_record.get("accepted") is not True:
            return True
        if payload_record.get("evidence_verdict") != "ADMISSIBLE_FINAL_FILM_SOURCE":
            return True
        if payload_record.get("self_attested") is not False:
            return True
        if payload_record.get("authority_classification") != "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY":
            return True

    return False


def _take_source_admissibility_authority_unbound(film_dir: Path) -> bool:
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    if not evidence_path.exists():
        return False

    evidence = _load_json(evidence_path)
    for record in evidence.get("admissible_sources", []):
        if record.get("admissibility_evidence_accepted") is not True:
            continue

        authority_id = record.get("authority_id")
        authority_record_path = record.get("authority_record_path")
        authority_record_sha256 = record.get("authority_record_sha256")

        if not authority_id or not authority_record_path or not authority_record_sha256:
            return True

        authority_path = Path(authority_record_path)
        if not authority_path.exists():
            return True

        try:
            authority_path.relative_to(film_dir)
        except ValueError:
            return True

        if _sha256_path(authority_path) != authority_record_sha256:
            return True

        try:
            authority = _load_json(authority_path)
        except json.JSONDecodeError:
            return True

        if authority.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_AUTHORITY":
            return True
        if authority.get("case_id") != evidence.get("case_id"):
            return True
        if authority.get("authority_id") != authority_id:
            return True
        if authority.get("authority_classification") != "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY":
            return True
        if authority.get("self_attested") is not False:
            return True
        if authority.get("may_certify_source_admissibility") is not True:
            return True

    return False


def _take_source_admissibility_authority_source_unbound(film_dir: Path) -> bool:
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    if not evidence_path.exists():
        return False

    evidence = _load_json(evidence_path)
    for record in evidence.get("admissible_sources", []):
        if record.get("admissibility_evidence_accepted") is not True:
            continue

        authority_record_path = record.get("authority_record_path")
        authority_record_sha256 = record.get("authority_record_sha256")
        if not authority_record_path or not authority_record_sha256:
            continue

        authority_path = Path(authority_record_path)
        if not authority_path.exists():
            continue

        try:
            authority_path.relative_to(film_dir)
        except ValueError:
            continue

        if _sha256_path(authority_path) != authority_record_sha256:
            continue

        try:
            authority = _load_json(authority_path)
        except json.JSONDecodeError:
            return True

        certified_sources = authority.get("certified_sources")
        if not isinstance(certified_sources, list):
            return True

        has_exact_binding = any(
            cert.get("authority_id") == record.get("authority_id")
            and cert.get("take_id") == record.get("take_id")
            and cert.get("source_sha256") == record.get("sha256")
            and cert.get("evidence_sha256") == record.get("evidence_sha256")
            and cert.get("source_admissibility_classification") == "ADMISSIBLE_FINAL_FILM_SOURCE"
            for cert in certified_sources
        )

        if not has_exact_binding:
            return True

    return False


def _take_source_admissibility_evidence_payload_authority_unbound(film_dir: Path) -> bool:
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    if not evidence_path.exists():
        return False

    evidence = _load_json(evidence_path)
    for record in evidence.get("admissible_sources", []):
        if record.get("admissibility_evidence_accepted") is not True:
            continue

        payload = record.get("evidence_file_path")
        expected_sha256 = record.get("evidence_sha256")
        if not payload or not expected_sha256:
            continue

        payload_path = Path(payload)
        if not payload_path.exists():
            continue

        try:
            payload_path.relative_to(film_dir)
        except ValueError:
            continue

        if _sha256_path(payload_path) != expected_sha256:
            continue

        try:
            payload_record = _load_json(payload_path)
        except json.JSONDecodeError:
            return True

        if payload_record.get("authority_id") != record.get("authority_id"):
            return True
        if payload_record.get("authority_record_path") != record.get("authority_record_path"):
            return True
        if payload_record.get("authority_record_sha256") != record.get("authority_record_sha256"):
            return True

    return False


def _take_source_admissibility_authority_grant_unbound(film_dir: Path) -> bool:
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    if not evidence_path.exists():
        return False

    evidence = _load_json(evidence_path)
    for record in evidence.get("admissible_sources", []):
        if record.get("admissibility_evidence_accepted") is not True:
            continue

        authority_record_path = record.get("authority_record_path")
        authority_record_sha256 = record.get("authority_record_sha256")
        if not authority_record_path or not authority_record_sha256:
            continue

        authority_path = Path(authority_record_path)
        if not authority_path.exists():
            continue

        try:
            authority_path.relative_to(film_dir)
        except ValueError:
            continue

        if _sha256_path(authority_path) != authority_record_sha256:
            continue

        try:
            authority = _load_json(authority_path)
        except json.JSONDecodeError:
            return True

        grant_path_value = authority.get("authority_grant_path")
        grant_sha256 = authority.get("authority_grant_sha256")
        grant_id = authority.get("authority_grant_id")

        if not grant_path_value or not grant_sha256 or not grant_id:
            return True

        grant_path = Path(grant_path_value)
        if not grant_path.exists():
            return True

        try:
            grant_path.relative_to(film_dir)
        except ValueError:
            return True

        if _sha256_path(grant_path) != grant_sha256:
            return True

        try:
            grant = _load_json(grant_path)
        except json.JSONDecodeError:
            return True

        if grant.get("grant_id") != grant_id:
            return True
        if grant.get("case_id") != record.get("case_id", evidence.get("case_id")):
            return True
        if grant.get("authority_id") != authority.get("authority_id"):
            return True
        if grant.get("authority_record_path") != authority_record_path:
            return True
        if grant.get("authority_record_sha256") != authority_record_sha256:
            return True
        if grant.get("grants_source_admissibility_authority") is not True:
            return True
        if grant.get("scope") != "TAKE_SOURCE_ADMISSIBILITY":
            return True
        if grant.get("revoked") is True:
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

    if _take_source_admissibility_evidence_payload_invalid(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_EVIDENCE_PAYLOAD_INVALID")

    if _take_source_admissibility_evidence_payload_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_EVIDENCE_PAYLOAD_UNBOUND")

    if _take_source_admissibility_authority_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_AUTHORITY_UNBOUND")

    if _take_source_admissibility_authority_source_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_AUTHORITY_SOURCE_UNBOUND")

    if _take_source_admissibility_evidence_payload_authority_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_EVIDENCE_PAYLOAD_AUTHORITY_UNBOUND")

    if _take_source_admissibility_authority_grant_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_AUTHORITY_GRANT_UNBOUND")

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
