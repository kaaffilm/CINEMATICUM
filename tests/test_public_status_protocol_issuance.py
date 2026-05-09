from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_status_declares_protocol_film_issuance_without_media_payload():
    status = (ROOT / "PUBLIC_STATUS.md").read_text()
    issuance = json.loads((ROOT / "CINEMATICUM_PROTOCOL_ISSUANCE.json").read_text())

    claim = "CINEMATICUM is a real protocol perimeter and a issued film."

    assert issuance["canonical_claim"] == claim
    assert issuance["issued"] is True
    assert issuance["issuance_type"] == "PROTOCOL_FILM"
    assert issuance["protocol_perimeter_issued"] is True
    assert issuance["protocol_film_issued"] is True
    assert issuance["media_payload_present"] is False
    assert issuance["motion_picture_media_issuance_ready"] is False

    assert claim in status
    assert "issued=true" in status
    assert "issuance_type=PROTOCOL_FILM" in status
    assert "protocol_perimeter_issued=true" in status
    assert "protocol_film_issued=true" in status
    assert "media_present=false" in status
    assert "motion_picture_media_issuance_ready=false" in status


def test_public_status_no_longer_contains_bare_issued_false_claim():
    status = (ROOT / "PUBLIC_STATUS.md").read_text()

    assert "issued=false" not in status
    assert "This status page does not issue a film." not in status
    assert "CINEMATICUM protocol-film issuance is not final-master media issuance." in status
