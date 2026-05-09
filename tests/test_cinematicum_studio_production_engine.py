import json
import subprocess
import sys
from pathlib import Path

from cinematicum_studio.core.db import init_db, connect
from cinematicum_studio.issuance_bridge.validate_master import validate_master_ready
from cinematicum_studio.issuance_bridge.validate_admissibility import validate_admissible_motion_picture
from cinematicum_studio.issuance_bridge.validate_acceptance import validate_cinematic_acceptance
from cinematicum_studio.issuance_bridge.validate_postproduction import validate_postproduction_acceptance
from cinematicum_studio.issuance_bridge.validate_issuance import validate_issuance_ready
from cinematicum_studio.issuance_bridge.validate_state_advancement import validate_state_advancement, ISSUANCE_REQUIRED_TOKEN
from cinematicum_studio.issuance_bridge.validate_publication import validate_publication_ready
from cinematicum_studio.issuance_bridge.validate_distribution import validate_distribution_ready
from cinematicum_studio.issuance_bridge.validate_release_artifact import validate_release_artifact_ready
from cinematicum_studio.issuance_bridge.validate_permanence import validate_permanence_ready
from cinematicum_studio.issuance_bridge.validate_public_index import validate_public_index_ready
from cinematicum_studio.issuance_bridge.validate_public_claim import validate_public_claim_ready


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"


def test_production_state_forbids_media_absent_issuance():
    state = json.loads((ROOT / "CASES" / CASE_ID / "PRODUCTION_STATE.json").read_text())
    assert state["final_master_present"] is False
    assert state["issued"] is False
    assert state["may_issue"] is False
    assert state["blocking_reason"] == "NO_FINAL_MASTER_MEDIA"


def test_media_requirement_gate_exists():
    gate = json.loads((ROOT / "CASES" / CASE_ID / "MEDIA_REQUIREMENT_GATE.json").read_text())
    assert gate["if_missing"] == "ISSUANCE_FORBIDDEN"
    assert "final_master_present" in gate["required_before_issuance"]


def test_studio_db_initializes():
    path = init_db()
    assert path.exists()


def test_case_graph_files_exist():
    base = ROOT / "CASES" / CASE_ID / "FILM"
    for name in [
        "FILM_STATE.json",
        "SCENE_GRAPH.json",
        "SHOT_GRAPH.json",
        "CHARACTER_BIBLE.json",
        "LOCATION_BIBLE.json",
        "STYLE_BIBLE.json",
    ]:
        assert (base / name).exists(), name


def test_shot_graph_has_12_shots():
    graph = json.loads((ROOT / "CASES" / CASE_ID / "FILM" / "SHOT_GRAPH.json").read_text())
    assert len(graph["shots"]) == 12


def test_issuance_bridge_refuses_without_master():
    ok, missing = validate_master_ready("CASE_TEST_NO_MASTER")
    assert ok is False
    assert "FINAL_MASTER_MANIFEST.json" in missing


def test_local_render_proof_is_not_admissible_film():
    ok, missing = validate_admissible_motion_picture(CASE_ID)
    assert ok is False
    assert "LOCAL_RENDER_PROOF_NOT_FILM" in missing
    assert "CINEMATIC_QUALITY_ACCEPTED" in missing


def test_selected_takes_do_not_imply_cinematic_acceptance():
    ok, missing = validate_cinematic_acceptance(CASE_ID)
    assert ok is False
    assert "CONTINUITY_ACCEPTED" in missing
    assert "DIRECTORIAL_ACCEPTANCE_ACCEPTED" in missing


def test_cli_acceptance_and_admissibility_commands_execute():
    acceptance = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "acceptance-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"cinematic_acceptance": false' in acceptance.stdout
    assert "CONTINUITY_ACCEPTED" in acceptance.stdout
    assert "DIRECTORIAL_ACCEPTANCE_ACCEPTED" in acceptance.stdout

    admissibility = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "admissibility-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"admissible_motion_picture": false' in admissibility.stdout
    assert "ACCEPTANCE::CONTINUITY_ACCEPTED" in admissibility.stdout
    assert "ACCEPTANCE::DIRECTORIAL_ACCEPTANCE_ACCEPTED" in admissibility.stdout


def test_postproduction_and_public_verdict_gate_film_admissibility():
    ok, missing = validate_postproduction_acceptance(CASE_ID)
    assert ok is False
    assert "SOUND_MIX_ACCEPTED" in missing
    assert "COLOR_GRADE_ACCEPTED" in missing
    assert "FINAL_CUT_ACCEPTED" in missing
    assert "PUBLIC_ADMISSIBILITY_VERDICT_ACCEPTED" in missing


def test_cli_postproduction_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "postproduction-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"postproduction_acceptance": false' in result.stdout
    assert "FINAL_CUT_ACCEPTED" in result.stdout


def test_issuance_requires_admissible_motion_picture():
    ok, missing = validate_issuance_ready(CASE_ID)
    assert ok is False
    assert "MASTER::FINAL_MASTER_MANIFEST.json" in missing
    assert any(item.startswith("ADMISSIBILITY::") for item in missing)


def test_cli_issuance_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "issuance-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["issuance_ready"] is False
    assert "MASTER::FINAL_MASTER_MANIFEST.json" in payload["missing"]
    assert any(item.startswith("ADMISSIBILITY::") for item in payload["missing"])

def test_state_advancement_to_issued_requires_issuance_ready():
    ok, missing = validate_state_advancement(CASE_ID, "ISSUED")
    assert ok is False
    assert ISSUANCE_REQUIRED_TOKEN in missing
    assert any(item.startswith("ISSUANCE::") for item in missing)


def test_state_advancement_to_nonterminal_state_does_not_require_issuance():
    ok, missing = validate_state_advancement(CASE_ID, "RELEASE_CANDIDATE_READY")
    assert ok is True
    assert missing == []


def test_cli_state_advancement_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "state-advancement-check", CASE_ID, "ISSUED"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["state_advancement_allowed"] is False
    assert ISSUANCE_REQUIRED_TOKEN in payload["missing"]
    assert any(item.startswith("ISSUANCE::") for item in payload["missing"])



def test_publication_requires_issuance_and_terminal_state():
    ok, missing = validate_publication_ready(CASE_ID)
    assert ok is False
    assert "ISSUANCE_READY_REQUIRED_FOR_PUBLICATION" in missing
    assert "TERMINAL_STATE_REQUIRED_FOR_PUBLICATION" in missing
    assert "CURRENT_STATE::RELEASE_CANDIDATE_READY" in missing
    assert "PUBLICATION_READINESS_ACCEPTED" in missing


def test_cli_publication_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "publication-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["publication_ready"] is False
    assert "ISSUANCE_READY_REQUIRED_FOR_PUBLICATION" in payload["missing"]
    assert "TERMINAL_STATE_REQUIRED_FOR_PUBLICATION" in payload["missing"]

def test_distribution_requires_publication_ready():
    ok, missing = validate_distribution_ready(CASE_ID)
    assert ok is False
    assert "PUBLICATION_READY_REQUIRED_FOR_DISTRIBUTION" in missing
    assert any(item.startswith("PUBLICATION::") for item in missing)
    assert "DISTRIBUTION_READINESS_ACCEPTED" in missing
    assert "PUBLIC_EXPORT_ALLOWED" in missing


def test_cli_distribution_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "distribution-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["distribution_ready"] is False
    assert "PUBLICATION_READY_REQUIRED_FOR_DISTRIBUTION" in payload["missing"]
    assert "DISTRIBUTION_READINESS_ACCEPTED" in payload["missing"]
    assert "PUBLIC_EXPORT_ALLOWED" in payload["missing"]

def test_release_artifact_requires_distribution_ready():
    ok, missing = validate_release_artifact_ready(CASE_ID)
    assert ok is False
    assert "DISTRIBUTION_READY_REQUIRED_FOR_RELEASE_ARTIFACT" in missing
    assert any(item.startswith("DISTRIBUTION::") for item in missing)
    assert "RELEASE_ARTIFACT_READINESS_ACCEPTED" in missing
    assert "RELEASE_ARTIFACT_ALLOWED" in missing
    assert "EXTERNAL_PACKAGE_ALLOWED" in missing


def test_cli_release_artifact_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "release-artifact-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["release_artifact_ready"] is False
    assert "DISTRIBUTION_READY_REQUIRED_FOR_RELEASE_ARTIFACT" in payload["missing"]
    assert "RELEASE_ARTIFACT_READINESS_ACCEPTED" in payload["missing"]
    assert "EXTERNAL_PACKAGE_ALLOWED" in payload["missing"]

def test_permanence_requires_release_artifact_ready():
    ok, missing = validate_permanence_ready(CASE_ID)
    assert ok is False
    assert "RELEASE_ARTIFACT_READY_REQUIRED_FOR_PERMANENCE" in missing
    assert any(item.startswith("RELEASE_ARTIFACT::") for item in missing)
    assert "PERMANENCE_READINESS_ACCEPTED" in missing
    assert "ARCHIVE_LOCK_ALLOWED" in missing
    assert "PERMANENT_PUBLIC_RECORD_ALLOWED" in missing
    assert "IMMUTABLE_RELEASE_REFERENCE_ALLOWED" in missing


def test_cli_permanence_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "permanence-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["permanence_ready"] is False
    assert "RELEASE_ARTIFACT_READY_REQUIRED_FOR_PERMANENCE" in payload["missing"]
    assert "PERMANENCE_READINESS_ACCEPTED" in payload["missing"]
    assert "IMMUTABLE_RELEASE_REFERENCE_ALLOWED" in payload["missing"]

def test_public_index_requires_permanence_ready():
    ok, missing = validate_public_index_ready(CASE_ID)
    assert ok is False
    assert "PERMANENCE_READY_REQUIRED_FOR_PUBLIC_INDEX" in missing
    assert any(item.startswith("PERMANENCE::") for item in missing)
    assert "CANONICAL_PUBLIC_INDEX_READINESS_ACCEPTED" in missing
    assert "CANONICAL_PUBLIC_INDEX_ALLOWED" in missing
    assert "PUBLIC_DISCOVERY_RECORD_ALLOWED" in missing
    assert "EXTERNAL_REFERENCE_ALLOWED" in missing


def test_cli_public_index_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "public-index-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["public_index_ready"] is False
    assert "PERMANENCE_READY_REQUIRED_FOR_PUBLIC_INDEX" in payload["missing"]
    assert "CANONICAL_PUBLIC_INDEX_READINESS_ACCEPTED" in payload["missing"]
    assert "EXTERNAL_REFERENCE_ALLOWED" in payload["missing"]

def test_public_claim_requires_public_index_ready():
    ok, missing = validate_public_claim_ready(CASE_ID)
    assert ok is False
    assert "PUBLIC_INDEX_READY_REQUIRED_FOR_PUBLIC_CLAIM" in missing
    assert any(item.startswith("PUBLIC_INDEX::") for item in missing)
    assert "PUBLIC_CLAIM_READINESS_ACCEPTED" in missing
    assert "PUBLIC_CLAIM_ALLOWED" in missing
    assert "ANNOUNCEMENT_ALLOWED" in missing
    assert "PROMOTIONAL_SURFACE_ALLOWED" in missing
    assert "PRESS_STATEMENT_ALLOWED" in missing


def test_cli_public_claim_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "public-claim-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["public_claim_ready"] is False
    assert "PUBLIC_INDEX_READY_REQUIRED_FOR_PUBLIC_CLAIM" in payload["missing"]
    assert "PUBLIC_CLAIM_READINESS_ACCEPTED" in payload["missing"]
    assert "PRESS_STATEMENT_ALLOWED" in payload["missing"]

