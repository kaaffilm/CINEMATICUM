from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_status_declares_protocol_film_issuance_without_media_payload():
    status = (ROOT / "PUBLIC_STATUS.md").read_text()
    issuance = json.loads((ROOT / "CINEMATICUM_PROTOCOL_ISSUANCE.json").read_text())

    claim = "CINEMATICUM is issued as a public replayable hash-bound protocol-film perimeter."

    assert issuance["canonical_claim"] == claim
    assert issuance["protocol_issued"] is True
    assert issuance["issued"] is False
    assert issuance["issuance_type"] == "PROTOCOL_FILM"
    assert issuance["protocol_perimeter_issued"] is True
    assert issuance["protocol_film_issued"] is True
    assert issuance["media_payload_present"] is False
    assert issuance["motion_picture_media_issuance_ready"] is False

    assert claim in status
    assert "protocol_issued=true" in status
    assert "issued=false" in status
    assert "issuance_type=PROTOCOL_FILM" in status
    assert "protocol_perimeter_issued=true" in status
    assert "protocol_film_issued=true" in status
    assert "media_present=false" in status
    assert "motion_picture_media_issuance_ready=false" in status


def test_public_status_omits_bare_issued_from_public_status():
    status = (ROOT / "PUBLIC_STATUS.md").read_text()

    assert re.search(r"(?m)^\s+issued=false\s*$", status) is None
    assert re.search(r"(?m)^\s+motion_picture_media_issued=false\s*$", status) is not None
    assert "Bare `issued` is reserved for motion-picture media issuance and remains false." in status
    assert "CINEMATICUM protocol-film issuance is not final-master media issuance." in status
