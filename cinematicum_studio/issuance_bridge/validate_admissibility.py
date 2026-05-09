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


def _take_source_admissibility_authority_grant_issuer_unbound(film_dir: Path) -> bool:
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
        if not grant_path_value or not grant_sha256:
            continue

        grant_path = Path(grant_path_value)
        if not grant_path.exists():
            continue

        try:
            grant_path.relative_to(film_dir)
        except ValueError:
            continue

        if _sha256_path(grant_path) != grant_sha256:
            continue

        try:
            grant = _load_json(grant_path)
        except json.JSONDecodeError:
            return True

        issuer_id = grant.get("grant_issuer_id")
        issuer_record_path = grant.get("grant_issuer_record_path")
        issuer_record_sha256 = grant.get("grant_issuer_record_sha256")

        if not issuer_id or not issuer_record_path or not issuer_record_sha256:
            return True

        issuer_path = Path(issuer_record_path)
        if not issuer_path.exists():
            return True

        try:
            issuer_path.relative_to(film_dir)
        except ValueError:
            return True

        if _sha256_path(issuer_path) != issuer_record_sha256:
            return True

        try:
            issuer = _load_json(issuer_path)
        except json.JSONDecodeError:
            return True

        if issuer.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_GRANT_ISSUER":
            return True
        if issuer.get("case_id") != evidence.get("case_id"):
            return True
        if issuer.get("issuer_id") != issuer_id:
            return True
        if issuer.get("self_attested") is not False:
            return True
        if issuer.get("may_issue_take_source_admissibility_authority_grants") is not True:
            return True

        issued_grants = issuer.get("issued_grants")
        if not isinstance(issued_grants, list):
            return True

        has_exact_grant = any(
            item.get("grant_id") == grant.get("grant_id")
            and item.get("authority_id") == grant.get("authority_id")
            and item.get("scope") == "TAKE_SOURCE_ADMISSIBILITY"
            and item.get("authority_record_path") == grant.get("authority_record_path")
            and item.get("authority_record_sha256") == grant.get("authority_record_sha256")
            and item.get("grants_source_admissibility_authority") is True
            and item.get("revoked") is not True
            for item in issued_grants
        )

        if not has_exact_grant:
            return True

    return False


def _take_source_admissibility_authority_grant_issuer_root_unbound(film_dir: Path) -> bool:
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
        if not grant_path_value or not grant_sha256:
            continue

        grant_path = Path(grant_path_value)
        if not grant_path.exists():
            continue

        try:
            grant_path.relative_to(film_dir)
        except ValueError:
            continue

        if _sha256_path(grant_path) != grant_sha256:
            continue

        try:
            grant = _load_json(grant_path)
        except json.JSONDecodeError:
            return True

        issuer_id = grant.get("grant_issuer_id")
        issuer_record_path = grant.get("grant_issuer_record_path")
        issuer_record_sha256 = grant.get("grant_issuer_record_sha256")

        if not issuer_id or not issuer_record_path or not issuer_record_sha256:
            continue

        issuer_path = Path(issuer_record_path)
        if not issuer_path.exists():
            continue

        try:
            issuer_path.relative_to(film_dir)
        except ValueError:
            continue

        if _sha256_path(issuer_path) != issuer_record_sha256:
            continue

        try:
            issuer = _load_json(issuer_path)
        except json.JSONDecodeError:
            return True

        root_authority_id = issuer.get("root_authority_id")
        root_authority_record_path = issuer.get("root_authority_record_path")
        root_authority_record_sha256 = issuer.get("root_authority_record_sha256")

        if not root_authority_id or not root_authority_record_path or not root_authority_record_sha256:
            return True

        root_path = Path(root_authority_record_path)
        if not root_path.exists():
            return True

        try:
            root_path.relative_to(film_dir)
        except ValueError:
            return True

        if _sha256_path(root_path) != root_authority_record_sha256:
            return True

        try:
            root = _load_json(root_path)
        except json.JSONDecodeError:
            return True

        if root.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY":
            return True
        if root.get("case_id") != evidence.get("case_id"):
            return True
        if root.get("root_authority_id") != root_authority_id:
            return True
        if root.get("self_attested") is not False:
            return True
        if root.get("may_authorize_take_source_admissibility_grant_issuers") is not True:
            return True

        authorized_issuers = root.get("authorized_grant_issuers")
        if not isinstance(authorized_issuers, list):
            return True

        has_exact_issuer = any(
            item.get("issuer_id") == issuer_id
            and item.get("scope") == "TAKE_SOURCE_ADMISSIBILITY"
            and item.get("may_issue_take_source_admissibility_authority_grants") is True
            and item.get("revoked") is not True
            for item in authorized_issuers
        )

        if not has_exact_issuer:
            return True

    return False


def _take_source_admissibility_root_authority_case_closure_unbound(film_dir: Path) -> bool:
    evidence_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    if not evidence_dir.exists():
        return False

    for root_path in evidence_dir.glob("*.json"):
        try:
            root = _load_json(root_path)
        except json.JSONDecodeError:
            continue

        if root.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY":
            continue

        root_authority_id = root.get("root_authority_id")
        closure_id = root.get("case_authority_closure_id")
        closure_path_value = root.get("case_authority_closure_path")
        closure_sha256 = root.get("case_authority_closure_sha256")

        if not root_authority_id or not closure_id or not closure_path_value or not closure_sha256:
            return True

        closure_path = Path(closure_path_value)
        if not closure_path.exists():
            return True

        try:
            closure_path.relative_to(film_dir)
        except ValueError:
            return True

        if _sha256_path(closure_path) != closure_sha256:
            return True

        try:
            closure = _load_json(closure_path)
        except json.JSONDecodeError:
            return True

        if closure.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE":
            return True
        if closure.get("case_id") != root.get("case_id"):
            return True
        if closure.get("closure_id") != closure_id:
            return True
        if closure.get("root_authority_id") != root_authority_id:
            return True
        if closure.get("closure_authorizes_root_authority") is not True:
            return True
        if closure.get("scope") != "TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY":
            return True
        if closure.get("revoked") is True:
            return True

        authorized_roots = closure.get("authorized_root_authorities")
        if not isinstance(authorized_roots, list):
            return True

        has_exact_root = any(
            item.get("root_authority_id") == root_authority_id
            and item.get("scope") == "TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY"
            and item.get("closure_authorizes_root_authority") is True
            and item.get("revoked") is not True
            for item in authorized_roots
        )

        if not has_exact_root:
            return True

    return False


def _take_source_admissibility_case_closure_admission_unbound(film_dir: Path) -> bool:
    evidence_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    if not evidence_dir.exists():
        return False

    for closure_path in evidence_dir.glob("*.json"):
        try:
            closure = _load_json(closure_path)
        except json.JSONDecodeError:
            continue

        if closure.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE":
            continue

        admission_path_value = closure.get("authority_object_admission_decision_path")
        admission_sha256 = closure.get("authority_object_admission_decision_sha256")
        admission_object_id = closure.get("authority_object_admission_object_id")

        if not admission_path_value or not admission_sha256 or not admission_object_id:
            return True

        admission_path = Path(admission_path_value)
        if not admission_path.exists():
            return True

        try:
            admission_path.relative_to(Path("CASES") / closure.get("case_id", ""))
        except ValueError:
            return True

        if _sha256_path(admission_path) != admission_sha256:
            return True

        try:
            admission = _load_json(admission_path)
        except json.JSONDecodeError:
            return True

        if admission.get("case_id") != closure.get("case_id"):
            return True
        if admission.get("object_id") != admission_object_id:
            return True
        if admission.get("accepted") is not True:
            return True
        if admission.get("decision") not in {"ACCEPT", "ACCEPTED"}:
            return True

        admitted_type = admission.get("admitted_object_type") or admission.get("object_type_admitted")
        if admitted_type != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE":
            return True

        if admission.get("admitted_closure_id") != closure.get("closure_id"):
            return True
        if admission.get("admitted_root_authority_id") != closure.get("root_authority_id"):
            return True

    return False


def _take_source_admissibility_case_closure_admission_ledger_unbound(film_dir: Path) -> bool:
    evidence_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    if not evidence_dir.exists():
        return False

    ledger_path = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json")

    for closure_path in evidence_dir.glob("*.json"):
        try:
            closure = _load_json(closure_path)
        except json.JSONDecodeError:
            continue

        if closure.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE":
            continue

        admission_path_value = closure.get("authority_object_admission_decision_path")
        admission_sha256 = closure.get("authority_object_admission_decision_sha256")
        admission_object_id = closure.get("authority_object_admission_object_id")

        # Prior gate owns malformed / missing admission references.
        if not admission_path_value or not admission_sha256 or not admission_object_id:
            continue

        if not ledger_path.exists():
            return True

        try:
            ledger = _load_json(ledger_path)
        except json.JSONDecodeError:
            return True

        if ledger.get("case_id") != closure.get("case_id"):
            return True

        decision_records = ledger.get("decision_records")
        if not isinstance(decision_records, list):
            return True

        def field(record, *names):
            for name in names:
                if name in record:
                    return record.get(name)
            return None

        has_ledger_entry = any(
            field(record, "object_id", "admission_object_id", "decision_object_id") == admission_object_id
            and field(record, "decision_path", "decision_file_path", "file_path", "path") == admission_path_value
            and field(record, "decision_sha256", "admission_decision_sha256", "sha256") == admission_sha256
            and record.get("decision") in {"ACCEPT", "ACCEPTED"}
            and record.get("accepted") is True
            and (
                record.get("admitted_object_type")
                or record.get("object_type_admitted")
            ) == "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE"
            and record.get("admitted_closure_id") == closure.get("closure_id")
            and record.get("admitted_root_authority_id") == closure.get("root_authority_id")
            for record in decision_records
        )

        if not has_ledger_entry:
            return True

    return False


def _take_source_admissibility_case_closure_admission_ledger_status_unbound(film_dir: Path) -> bool:
    evidence_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    if not evidence_dir.exists():
        return False

    ledger_path = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json")
    if not ledger_path.exists():
        return False

    try:
        ledger = _load_json(ledger_path)
    except json.JSONDecodeError:
        return True

    def field(record, *names):
        for name in names:
            if name in record:
                return record.get(name)
        return None

    for closure_path in evidence_dir.glob("*.json"):
        try:
            closure = _load_json(closure_path)
        except json.JSONDecodeError:
            continue

        if closure.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE":
            continue

        case_id = closure.get("case_id")
        admission_path_value = closure.get("authority_object_admission_decision_path")
        admission_sha256 = closure.get("authority_object_admission_decision_sha256")
        admission_object_id = closure.get("authority_object_admission_object_id")

        # Earlier gates own malformed closure/admission references.
        if not case_id or not admission_path_value or not admission_sha256 or not admission_object_id:
            continue

        decision_records = ledger.get("decision_records")
        if not isinstance(decision_records, list):
            continue

        matching_records = [
            record
            for record in decision_records
            if field(record, "object_id", "admission_object_id", "decision_object_id") == admission_object_id
            and field(record, "decision_path", "decision_file_path", "file_path", "path") == admission_path_value
            and field(record, "decision_sha256", "admission_decision_sha256", "sha256") == admission_sha256
            and record.get("decision") in {"ACCEPT", "ACCEPTED"}
            and record.get("accepted") is True
            and (
                record.get("admitted_object_type")
                or record.get("object_type_admitted")
            ) == "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE"
            and record.get("admitted_closure_id") == closure.get("closure_id")
            and record.get("admitted_root_authority_id") == closure.get("root_authority_id")
        ]

        # Earlier ledger gate owns absence of the entry.
        if not matching_records:
            continue

        status_path = Path("CASES") / case_id / "AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_STATUS.json"
        if not status_path.exists():
            return True

        try:
            status = _load_json(status_path)
        except json.JSONDecodeError:
            return True

        mirror_keys = (
            "case_id",
            "current_state",
            "active_current_state",
            "decision_record_count",
            "admission_decision_count",
            "accepted_decision_count",
            "rejected_decision_count",
            "decision_records_present",
            "accepted_decisions_present",
            "rejected_decisions_present",
            "authority_satisfied",
            "may_advance_now",
            "release_candidate_ready",
            "issued",
            "media_present",
        )

        for key in mirror_keys:
            if status.get(key) != ledger.get(key):
                return True

        accepted_count = sum(
            1
            for record in decision_records
            if record.get("decision") in {"ACCEPT", "ACCEPTED"} and record.get("accepted") is True
        )
        rejected_count = sum(
            1
            for record in decision_records
            if record.get("decision") == "REJECTED" or record.get("accepted") is False
        )

        if ledger.get("decision_record_count") != len(decision_records):
            return True
        if ledger.get("admission_decision_count") != len(decision_records):
            return True
        if ledger.get("accepted_decision_count") != accepted_count:
            return True
        if ledger.get("rejected_decision_count") != rejected_count:
            return True
        if ledger.get("decision_records_present") is not (len(decision_records) > 0):
            return True
        if ledger.get("accepted_decisions_present") is not (accepted_count > 0):
            return True
        if ledger.get("rejected_decisions_present") is not (rejected_count > 0):
            return True

    return False


def _take_source_admissibility_case_closure_admission_docket_unbound(film_dir: Path) -> bool:
    evidence_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    if not evidence_dir.exists():
        return False

    docket_path = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
    if not docket_path.exists():
        return False

    try:
        docket = _load_json(docket_path)
    except json.JSONDecodeError:
        return True

    def field(record, *names):
        for name in names:
            if name in record:
                return record.get(name)
        return None

    for closure_path in evidence_dir.glob("*.json"):
        try:
            closure = _load_json(closure_path)
        except json.JSONDecodeError:
            continue

        if closure.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE":
            continue

        case_id = closure.get("case_id")
        admission_path_value = closure.get("authority_object_admission_decision_path")
        admission_sha256 = closure.get("authority_object_admission_decision_sha256")
        admission_object_id = closure.get("authority_object_admission_object_id")

        # Earlier gates own malformed closure/admission references.
        if not case_id or not admission_path_value or not admission_sha256 or not admission_object_id:
            continue

        if docket.get("case_id") != case_id:
            return True
        if docket.get("object_type") != "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET":
            return True
        if docket.get("authority_object_admission_docket_passed") is not True:
            return True
        if docket.get("authority_objects_admitted") is not True:
            return True

        docket_records = None
        for key in (
            "admitted_authority_objects",
            "authority_object_admissions",
            "admission_records",
            "admitted_objects",
            "docket_records",
        ):
            value = docket.get(key)
            if isinstance(value, list):
                docket_records = value
                break

        if docket_records is None:
            return True

        has_docket_entry = any(
            field(record, "object_id", "admission_object_id", "decision_object_id") == admission_object_id
            and field(record, "decision_path", "decision_file_path", "file_path", "path") == admission_path_value
            and field(record, "decision_sha256", "admission_decision_sha256", "sha256") == admission_sha256
            and field(record, "decision", "admission_decision") in {"ACCEPT", "ACCEPTED"}
            and field(record, "accepted", "admitted") is True
            and (
                field(record, "admitted_object_type", "object_type_admitted")
                == "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE"
            )
            and field(record, "admitted_closure_id", "closure_id") == closure.get("closure_id")
            and field(record, "admitted_root_authority_id", "root_authority_id") == closure.get("root_authority_id")
            for record in docket_records
        )

        if not has_docket_entry:
            return True

    return False


def _take_source_admissibility_case_closure_admission_docket_status_unbound(film_dir: Path) -> bool:
    evidence_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    if not evidence_dir.exists():
        return False

    docket_path = Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
    status_path = film_dir.parents[1] / "AUTHORITY_OBJECT_ADMISSION_DOCKET_STATUS.json"

    if not docket_path.exists():
        return False

    try:
        docket = _load_json(docket_path)
    except json.JSONDecodeError:
        return True

    if not status_path.exists():
        status = None
    else:
        try:
            status = _load_json(status_path)
        except json.JSONDecodeError:
            return True

    def field(record, *names):
        for name in names:
            if name in record:
                return record.get(name)
        return None

    def docket_records(payload):
        for key in (
            "admitted_authority_objects",
            "authority_object_admissions",
            "admission_records",
            "admitted_objects",
            "docket_records",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return None

    records = docket_records(docket)
    if records is None:
        return False

    for closure_path in evidence_dir.glob("*.json"):
        try:
            closure = _load_json(closure_path)
        except json.JSONDecodeError:
            continue

        if closure.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE":
            continue

        case_id = closure.get("case_id")
        admission_path_value = closure.get("authority_object_admission_decision_path")
        admission_sha256 = closure.get("authority_object_admission_decision_sha256")
        admission_object_id = closure.get("authority_object_admission_object_id")
        closure_id = closure.get("closure_id")
        root_authority_id = closure.get("root_authority_id")

        # Earlier gates own malformed closure/admission/docket references.
        if not all([case_id, admission_path_value, admission_sha256, admission_object_id, closure_id, root_authority_id]):
            continue

        has_docket_entry = any(
            field(record, "object_id", "admission_object_id", "decision_object_id") == admission_object_id
            and field(record, "decision_path", "decision_file_path", "file_path", "path") == admission_path_value
            and field(record, "decision_sha256", "admission_decision_sha256", "sha256") == admission_sha256
            and field(record, "decision", "admission_decision") in {"ACCEPT", "ACCEPTED"}
            and field(record, "accepted", "admitted") is True
            and field(record, "admitted_closure_id", "closure_id") == closure_id
            and field(record, "admitted_root_authority_id", "root_authority_id") == root_authority_id
            for record in records
        )

        if not has_docket_entry:
            continue

        if status is None:
            return True

        if status.get("case_id") != case_id:
            return True
        if status.get("authority_object_admission_docket_passed") != docket.get("authority_object_admission_docket_passed"):
            return True
        if status.get("authority_objects_admitted") != docket.get("authority_objects_admitted"):
            return True
        if status.get("accepted_authority_object_count") != docket.get("accepted_authority_object_count"):
            return True
        if status.get("instantiated_authority_object_count") != docket.get("instantiated_authority_object_count"):
            return True
        if status.get("unfilled_authority_object_slot_count") != docket.get("unfilled_authority_object_slot_count"):
            return True

        status_records = docket_records(status)
        if status_records is None:
            return True

        has_status_entry = any(
            field(record, "object_id", "admission_object_id", "decision_object_id") == admission_object_id
            and field(record, "decision_path", "decision_file_path", "file_path", "path") == admission_path_value
            and field(record, "decision_sha256", "admission_decision_sha256", "sha256") == admission_sha256
            and field(record, "decision", "admission_decision") in {"ACCEPT", "ACCEPTED"}
            and field(record, "accepted", "admitted") is True
            and field(record, "admitted_closure_id", "closure_id") == closure_id
            and field(record, "admitted_root_authority_id", "root_authority_id") == root_authority_id
            for record in status_records
        )

        if not has_status_entry:
            return True

    return False


def _take_source_admissibility_case_closure_admission_registry_unbound(film_dir: Path) -> bool:
    evidence_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    if not evidence_dir.exists():
        return False

    root_dir = film_dir.parents[2]
    registry_path = root_dir / "CINEMATICUM_OBJECT_REGISTRY.json"

    if not registry_path.exists():
        return True

    try:
        registry = _load_json(registry_path)
    except json.JSONDecodeError:
        return True

    entries = registry.get("entries")
    if not isinstance(entries, list):
        return True

    def field(record, *names):
        for name in names:
            if name in record:
                return record.get(name)
        return None

    for closure_path in evidence_dir.glob("*.json"):
        try:
            closure = _load_json(closure_path)
        except json.JSONDecodeError:
            continue

        if closure.get("object_type") != "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE":
            continue

        case_id = closure.get("case_id")
        closure_id = closure.get("closure_id")
        root_authority_id = closure.get("root_authority_id")
        admission_path_value = closure.get("authority_object_admission_decision_path")
        admission_sha256 = closure.get("authority_object_admission_decision_sha256")
        admission_object_id = closure.get("authority_object_admission_object_id")

        # Earlier gates own malformed closure/admission references.
        if not all([case_id, closure_id, root_authority_id, admission_path_value, admission_sha256, admission_object_id]):
            continue

        closure_rel = str(closure_path.relative_to(root_dir))

        has_registry_entry = any(
            field(entry, "path", "file_path") == closure_rel
            and field(entry, "object_type") == "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE"
            and field(entry, "case_id") == case_id
            and field(entry, "closure_id") == closure_id
            and field(entry, "root_authority_id") == root_authority_id
            and field(entry, "authority_object_admission_decision_path", "admission_decision_path") == admission_path_value
            and field(entry, "authority_object_admission_decision_sha256", "admission_decision_sha256") == admission_sha256
            and field(entry, "authority_object_admission_object_id", "admission_object_id") == admission_object_id
            for entry in entries
        )

        if not has_registry_entry:
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

    if _take_source_admissibility_authority_grant_issuer_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_AUTHORITY_GRANT_ISSUER_UNBOUND")

    if _take_source_admissibility_authority_grant_issuer_root_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_AUTHORITY_GRANT_ISSUER_ROOT_UNBOUND")

    if _take_source_admissibility_root_authority_case_closure_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_ROOT_AUTHORITY_CASE_CLOSURE_UNBOUND")

    if _take_source_admissibility_case_closure_admission_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_CASE_CLOSURE_ADMISSION_UNBOUND")

    if _take_source_admissibility_case_closure_admission_ledger_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_CASE_CLOSURE_ADMISSION_LEDGER_UNBOUND")

    if _take_source_admissibility_case_closure_admission_ledger_status_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_CASE_CLOSURE_ADMISSION_LEDGER_STATUS_UNBOUND")

    if _take_source_admissibility_case_closure_admission_docket_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_CASE_CLOSURE_ADMISSION_DOCKET_UNBOUND")

    if _take_source_admissibility_case_closure_admission_docket_status_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_CASE_CLOSURE_ADMISSION_DOCKET_STATUS_UNBOUND")

    if _take_source_admissibility_case_closure_admission_registry_unbound(film_dir):
        missing.append("TAKE_SOURCE_ADMISSIBILITY_CASE_CLOSURE_ADMISSION_REGISTRY_UNBOUND")

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
