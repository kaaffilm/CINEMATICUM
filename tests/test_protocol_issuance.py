from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_protocol_issuance import (
    validate_protocol_issuance,
)
from cinematicum_studio.issuance_bridge.validate_issuance import validate_issuance_ready


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"


def test_protocol_film_is_issued_without_media_payload():
    ok, missing = validate_protocol_issuance(CASE_ID)

    assert ok is True
    assert missing == []

    data = json.loads((ROOT / "CINEMATICUM_PROTOCOL_ISSUANCE.json").read_text())

    assert data["canonical_claim"] == "CINEMATICUM is issued as a public replayable hash-bound protocol-film perimeter."
    assert data["protocol_issued"] is True
    assert data["issued"] is False
    assert data["issuance_type"] == "PROTOCOL_FILM"
    assert data["protocol_perimeter_issued"] is True
    assert data["protocol_film_issued"] is True
    assert data["media_payload_present"] is False
    assert data["private_access_required"] is False


def test_motion_picture_media_issuance_remains_separate_from_protocol_film_issuance():
    media_ok, media_missing = validate_issuance_ready(CASE_ID)
    protocol_ok, protocol_missing = validate_protocol_issuance(CASE_ID)

    assert protocol_ok is True
    assert protocol_missing == []

    assert media_ok is False
    assert "ADMISSIBILITY::LOCAL_RENDER_PROOF_NOT_FILM" in media_missing


def test_issuance_check_reports_protocol_issued_and_media_not_ready():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "issuance-check", CASE_ID],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)

    assert data["protocol_issued"] is True
    assert data["issued"] is False
    assert data["issuance_type"] == "PROTOCOL_FILM"
    assert data["protocol_perimeter_issued"] is True
    assert data["protocol_film_issued"] is True
    assert data["media_payload_present"] is False
    assert data["motion_picture_media_issuance_ready"] is False
    assert "issuance_ready" not in data


def test_outsider_replay_prints_protocol_issuance_not_bare_non_issuance():
    result = subprocess.run(
        ["bash", "scripts/verify-outsider-clone-replay.sh"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "CINEMATICUM OUTSIDER CLONE REPLAY: PASS" in result.stdout
    assert "ISSUED=false" in result.stdout
    assert "ADMISSIBLE_MOTION_PICTURE_ISSUED=false" in result.stdout
    assert "MOTION_PICTURE_ISSUED=false" in result.stdout
    assert "MOTION_PICTURE_MEDIA_ISSUANCE_READY=false" in result.stdout
    assert "MEDIA_PRESENT=false" in result.stdout
    assert "ISSUED=true" not in result.stdout
    assert "ADMISSIBLE_MOTION_PICTURE_ISSUED=true" not in result.stdout
    assert "MOTION_PICTURE_ISSUED=true" not in result.stdout

