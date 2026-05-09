from __future__ import annotations

import json
from pathlib import Path


def validate_protocol_issuance(case_id: str) -> tuple[bool, list[str]]:
    missing: list[str] = []
    path = Path("CINEMATICUM_PROTOCOL_ISSUANCE.json")

    if not path.exists():
        return False, ["CINEMATICUM_PROTOCOL_ISSUANCE.json"]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False, ["CINEMATICUM_PROTOCOL_ISSUANCE_INVALID_JSON"]

    required = {
        "object_type": "CINEMATICUM_PROTOCOL_ISSUANCE",
        "case_id": case_id,
        "film_identity": "CINEMATICUM",
        "issued": True,
        "protocol_perimeter_issued": True,
        "protocol_film_issued": True,
        "issuance_type": "PROTOCOL_FILM",
        "issued_object": "PUBLIC_REPLAYABLE_HASH_BOUND_PROTOCOL_PERIMETER",
        "media_payload_present": False,
        "model_weight_payload_present": False,
        "private_access_required": False,
        "network_required_after_clone": False,
        "fresh_checkout_can_verify": True,
        "media_payload_issuance_is_not_required_for_protocol_film_issuance": True,
    }

    for key, expected in required.items():
        if data.get(key) != expected:
            missing.append(f"PROTOCOL_ISSUANCE::{key}")

    claim = data.get("canonical_claim")
    if claim != "CINEMATICUM is a real protocol perimeter and a issued film.":
        missing.append("PROTOCOL_ISSUANCE::CANONICAL_CLAIM")

    return len(missing) == 0, missing
