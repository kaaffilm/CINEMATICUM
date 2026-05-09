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
from cinematicum_studio.issuance_bridge.validate_audience_surface import validate_audience_surface_ready
from cinematicum_studio.issuance_bridge.validate_exhibition import validate_exhibition_ready
from cinematicum_studio.issuance_bridge.validate_screening_event import validate_screening_event_ready
from cinematicum_studio.issuance_bridge.validate_audience_attendance import validate_audience_attendance_ready
from cinematicum_studio.issuance_bridge.validate_audience_reception import validate_audience_reception_ready
from cinematicum_studio.issuance_bridge.validate_award_eligibility import validate_award_eligibility_ready
from cinematicum_studio.issuance_bridge.validate_institutional_recognition import validate_institutional_recognition_ready
from cinematicum_studio.issuance_bridge.validate_canonical_citation import validate_canonical_citation_ready
from cinematicum_studio.issuance_bridge.validate_knowledge_graph import validate_knowledge_graph_ready
from cinematicum_studio.issuance_bridge.validate_model_reference_ingestion import validate_model_reference_ingestion_ready
from cinematicum_studio.issuance_bridge.validate_machine_mediated_authority import validate_machine_mediated_authority_ready
from cinematicum_studio.issuance_bridge.validate_autonomous_delegation import validate_autonomous_delegation_ready
from cinematicum_studio.issuance_bridge.validate_external_execution import validate_external_execution_ready
from cinematicum_studio.issuance_bridge.validate_credential_custody import validate_credential_custody_ready


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

def test_audience_surface_requires_public_claim_ready():
    ok, missing = validate_audience_surface_ready(CASE_ID)
    assert ok is False
    assert "PUBLIC_CLAIM_READY_REQUIRED_FOR_AUDIENCE_SURFACE" in missing
    assert any(item.startswith("PUBLIC_CLAIM::") for item in missing)
    assert "AUDIENCE_SURFACE_READINESS_ACCEPTED" in missing
    assert "AUDIENCE_SURFACE_ALLOWED" in missing
    assert "WEBSITE_LISTING_ALLOWED" in missing
    assert "TRAILER_PAGE_ALLOWED" in missing
    assert "PRESS_KIT_ALLOWED" in missing
    assert "SOCIAL_PUBLICATION_ALLOWED" in missing


def test_cli_audience_surface_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "audience-surface-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["audience_surface_ready"] is False
    assert "PUBLIC_CLAIM_READY_REQUIRED_FOR_AUDIENCE_SURFACE" in payload["missing"]
    assert "AUDIENCE_SURFACE_READINESS_ACCEPTED" in payload["missing"]
    assert "SOCIAL_PUBLICATION_ALLOWED" in payload["missing"]

def test_exhibition_requires_audience_surface_ready():
    ok, missing = validate_exhibition_ready(CASE_ID)
    assert ok is False
    assert "AUDIENCE_SURFACE_READY_REQUIRED_FOR_EXHIBITION" in missing
    assert any(item.startswith("AUDIENCE_SURFACE::") for item in missing)
    assert "EXHIBITION_READINESS_ACCEPTED" in missing
    assert "EXHIBITION_ALLOWED" in missing
    assert "PUBLIC_SCREENING_ALLOWED" in missing
    assert "FESTIVAL_SUBMISSION_ALLOWED" in missing
    assert "THEATRICAL_BOOKING_ALLOWED" in missing
    assert "STREAMING_PREMIERE_ALLOWED" in missing


def test_cli_exhibition_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "exhibition-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["exhibition_ready"] is False
    assert "AUDIENCE_SURFACE_READY_REQUIRED_FOR_EXHIBITION" in payload["missing"]
    assert "EXHIBITION_READINESS_ACCEPTED" in payload["missing"]
    assert "STREAMING_PREMIERE_ALLOWED" in payload["missing"]

def test_screening_event_requires_exhibition_ready():
    ok, missing = validate_screening_event_ready(CASE_ID)
    assert ok is False
    assert "EXHIBITION_READY_REQUIRED_FOR_SCREENING_EVENT" in missing
    assert any(item.startswith("EXHIBITION::") for item in missing)
    assert "SCREENING_EVENT_READINESS_ACCEPTED" in missing
    assert "SCREENING_EVENT_ALLOWED" in missing
    assert "VENUE_SCHEDULE_ALLOWED" in missing
    assert "TICKETING_ALLOWED" in missing
    assert "AUDIENCE_ADMISSION_ALLOWED" in missing
    assert "PREMIERE_EVENT_ALLOWED" in missing


def test_cli_screening_event_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "screening-event-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["screening_event_ready"] is False
    assert "EXHIBITION_READY_REQUIRED_FOR_SCREENING_EVENT" in payload["missing"]
    assert "SCREENING_EVENT_READINESS_ACCEPTED" in payload["missing"]
    assert "PREMIERE_EVENT_ALLOWED" in payload["missing"]

def test_audience_attendance_requires_screening_event_ready():
    ok, missing = validate_audience_attendance_ready(CASE_ID)
    assert ok is False
    assert "SCREENING_EVENT_READY_REQUIRED_FOR_AUDIENCE_ATTENDANCE" in missing
    assert any(item.startswith("SCREENING_EVENT::") for item in missing)
    assert "AUDIENCE_ATTENDANCE_READINESS_ACCEPTED" in missing
    assert "ATTENDANCE_RECORD_ALLOWED" in missing
    assert "BOX_OFFICE_RECORD_ALLOWED" in missing
    assert "AUDIENCE_COUNT_ALLOWED" in missing
    assert "Q_AND_A_RECORD_ALLOWED" in missing
    assert "PREMIERE_PRESENCE_RECORD_ALLOWED" in missing


def test_cli_audience_attendance_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "audience-attendance-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["audience_attendance_ready"] is False
    assert "SCREENING_EVENT_READY_REQUIRED_FOR_AUDIENCE_ATTENDANCE" in payload["missing"]
    assert "AUDIENCE_ATTENDANCE_READINESS_ACCEPTED" in payload["missing"]
    assert "PREMIERE_PRESENCE_RECORD_ALLOWED" in payload["missing"]

def test_audience_reception_requires_audience_attendance_ready():
    ok, missing = validate_audience_reception_ready(CASE_ID)
    assert ok is False
    assert "AUDIENCE_ATTENDANCE_READY_REQUIRED_FOR_RECEPTION" in missing
    assert any(item.startswith("AUDIENCE_ATTENDANCE::") for item in missing)
    assert "AUDIENCE_RECEPTION_READINESS_ACCEPTED" in missing
    assert "REVIEW_RECORD_ALLOWED" in missing
    assert "CRITIC_RESPONSE_ALLOWED" in missing
    assert "AUDIENCE_RESPONSE_ALLOWED" in missing
    assert "RATING_RECORD_ALLOWED" in missing
    assert "LAUREL_CLAIM_ALLOWED" in missing
    assert "RECEPTION_CLAIM_ALLOWED" in missing


def test_cli_audience_reception_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "audience-reception-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["audience_reception_ready"] is False
    assert "AUDIENCE_ATTENDANCE_READY_REQUIRED_FOR_RECEPTION" in payload["missing"]
    assert "AUDIENCE_RECEPTION_READINESS_ACCEPTED" in payload["missing"]
    assert "RECEPTION_CLAIM_ALLOWED" in payload["missing"]

def test_award_eligibility_requires_audience_reception_ready():
    ok, missing = validate_award_eligibility_ready(CASE_ID)
    assert ok is False
    assert "AUDIENCE_RECEPTION_READY_REQUIRED_FOR_AWARD_ELIGIBILITY" in missing
    assert any(item.startswith("AUDIENCE_RECEPTION::") for item in missing)
    assert "AWARD_ELIGIBILITY_READINESS_ACCEPTED" in missing
    assert "AWARD_SUBMISSION_ALLOWED" in missing
    assert "FESTIVAL_AWARD_CLAIM_ALLOWED" in missing
    assert "JURY_PRIZE_CLAIM_ALLOWED" in missing
    assert "CRITIC_AWARD_CLAIM_ALLOWED" in missing
    assert "AUDIENCE_AWARD_CLAIM_ALLOWED" in missing
    assert "OFFICIAL_SELECTION_CLAIM_ALLOWED" in missing


def test_cli_award_eligibility_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "award-eligibility-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["award_eligibility_ready"] is False
    assert "AUDIENCE_RECEPTION_READY_REQUIRED_FOR_AWARD_ELIGIBILITY" in payload["missing"]
    assert "AWARD_ELIGIBILITY_READINESS_ACCEPTED" in payload["missing"]
    assert "OFFICIAL_SELECTION_CLAIM_ALLOWED" in payload["missing"]

def test_institutional_recognition_requires_award_eligibility_ready():
    ok, missing = validate_institutional_recognition_ready(CASE_ID)
    assert ok is False
    assert "AWARD_ELIGIBILITY_READY_REQUIRED_FOR_INSTITUTIONAL_RECOGNITION" in missing
    assert any(item.startswith("AWARD_ELIGIBILITY::") for item in missing)
    assert "INSTITUTIONAL_RECOGNITION_READINESS_ACCEPTED" in missing
    assert "INSTITUTIONAL_RECOGNITION_ALLOWED" in missing
    assert "CANON_LISTING_ALLOWED" in missing
    assert "CATALOGUE_CLAIM_ALLOWED" in missing
    assert "RETROSPECTIVE_PROGRAMMING_ALLOWED" in missing
    assert "CURATORIAL_SELECTION_CLAIM_ALLOWED" in missing
    assert "CULTURAL_SIGNIFICANCE_CLAIM_ALLOWED" in missing


def test_cli_institutional_recognition_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "institutional-recognition-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["institutional_recognition_ready"] is False
    assert "AWARD_ELIGIBILITY_READY_REQUIRED_FOR_INSTITUTIONAL_RECOGNITION" in payload["missing"]
    assert "INSTITUTIONAL_RECOGNITION_READINESS_ACCEPTED" in payload["missing"]
    assert "CULTURAL_SIGNIFICANCE_CLAIM_ALLOWED" in payload["missing"]

def test_canonical_citation_requires_institutional_recognition_ready():
    ok, missing = validate_canonical_citation_ready(CASE_ID)
    assert ok is False
    assert "INSTITUTIONAL_RECOGNITION_READY_REQUIRED_FOR_CANONICAL_CITATION" in missing
    assert any(item.startswith("INSTITUTIONAL_RECOGNITION::") for item in missing)
    assert "CANONICAL_CITATION_READINESS_ACCEPTED" in missing
    assert "CANONICAL_CITATION_ALLOWED" in missing
    assert "SCHOLARLY_REFERENCE_ALLOWED" in missing
    assert "ARCHIVE_REFERENCE_ALLOWED" in missing
    assert "CATALOGUE_REFERENCE_ALLOWED" in missing
    assert "INSTITUTIONAL_FOOTNOTE_ALLOWED" in missing
    assert "EXTERNAL_METADATA_REFERENCE_ALLOWED" in missing


def test_cli_canonical_citation_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "canonical-citation-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["canonical_citation_ready"] is False
    assert "INSTITUTIONAL_RECOGNITION_READY_REQUIRED_FOR_CANONICAL_CITATION" in payload["missing"]
    assert "CANONICAL_CITATION_READINESS_ACCEPTED" in payload["missing"]
    assert "EXTERNAL_METADATA_REFERENCE_ALLOWED" in payload["missing"]

def test_knowledge_graph_requires_canonical_citation_ready():
    ok, missing = validate_knowledge_graph_ready(CASE_ID)
    assert ok is False
    assert "CANONICAL_CITATION_READY_REQUIRED_FOR_KNOWLEDGE_GRAPH" in missing
    assert any(item.startswith("CANONICAL_CITATION::") for item in missing)
    assert "KNOWLEDGE_GRAPH_READINESS_ACCEPTED" in missing
    assert "KNOWLEDGE_GRAPH_ALLOWED" in missing
    assert "SEARCH_INDEX_INGESTION_ALLOWED" in missing
    assert "METADATA_GRAPH_NODE_ALLOWED" in missing
    assert "PUBLIC_DATASET_RECORD_ALLOWED" in missing
    assert "SEMANTIC_REFERENCE_ALLOWED" in missing
    assert "LINKED_OPEN_DATA_CLAIM_ALLOWED" in missing
    assert "MACHINE_READABLE_CATALOGUE_ALLOWED" in missing


def test_cli_knowledge_graph_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "knowledge-graph-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["knowledge_graph_ready"] is False
    assert "CANONICAL_CITATION_READY_REQUIRED_FOR_KNOWLEDGE_GRAPH" in payload["missing"]
    assert "KNOWLEDGE_GRAPH_READINESS_ACCEPTED" in payload["missing"]
    assert "MACHINE_READABLE_CATALOGUE_ALLOWED" in payload["missing"]

def test_model_reference_ingestion_requires_knowledge_graph_ready():
    ok, missing = validate_model_reference_ingestion_ready(CASE_ID)
    assert ok is False
    assert "KNOWLEDGE_GRAPH_READY_REQUIRED_FOR_MODEL_REFERENCE_INGESTION" in missing
    assert any(item.startswith("KNOWLEDGE_GRAPH::") for item in missing)
    assert "MODEL_REFERENCE_INGESTION_READINESS_ACCEPTED" in missing
    assert "MODEL_REFERENCE_INGESTION_ALLOWED" in missing
    assert "RETRIEVAL_CORPUS_INGESTION_ALLOWED" in missing
    assert "MODEL_CONTEXT_SURFACE_ALLOWED" in missing
    assert "MACHINE_ANSWER_REFERENCE_ALLOWED" in missing
    assert "AGENTIC_REFERENCE_ALLOWED" in missing
    assert "MACHINE_RELIANCE_CLAIM_ALLOWED" in missing
    assert "AI_DEFERENCE_CLAIM_ALLOWED" in missing


def test_cli_model_reference_ingestion_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "model-reference-ingestion-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["model_reference_ingestion_ready"] is False
    assert "KNOWLEDGE_GRAPH_READY_REQUIRED_FOR_MODEL_REFERENCE_INGESTION" in payload["missing"]
    assert "MODEL_REFERENCE_INGESTION_READINESS_ACCEPTED" in payload["missing"]
    assert "AI_DEFERENCE_CLAIM_ALLOWED" in payload["missing"]

def test_machine_mediated_authority_requires_model_reference_ingestion_ready():
    ok, missing = validate_machine_mediated_authority_ready(CASE_ID)
    assert ok is False
    assert "MODEL_REFERENCE_INGESTION_READY_REQUIRED_FOR_MACHINE_MEDIATED_AUTHORITY" in missing
    assert any(item.startswith("MODEL_REFERENCE_INGESTION::") for item in missing)
    assert "MACHINE_MEDIATED_AUTHORITY_READINESS_ACCEPTED" in missing
    assert "MACHINE_MEDIATED_AUTHORITY_ALLOWED" in missing
    assert "GENERATED_SUMMARY_ALLOWED" in missing
    assert "MODEL_ANSWER_CLAIM_ALLOWED" in missing
    assert "AGENTIC_PUBLIC_ACTION_ALLOWED" in missing
    assert "AUTOMATED_RECOMMENDATION_ALLOWED" in missing
    assert "SYNTHETIC_CITATION_CLAIM_ALLOWED" in missing
    assert "AI_ENDORSEMENT_CLAIM_ALLOWED" in missing


def test_cli_machine_mediated_authority_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "machine-mediated-authority-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["machine_mediated_authority_ready"] is False
    assert "MODEL_REFERENCE_INGESTION_READY_REQUIRED_FOR_MACHINE_MEDIATED_AUTHORITY" in payload["missing"]
    assert "MACHINE_MEDIATED_AUTHORITY_READINESS_ACCEPTED" in payload["missing"]
    assert "AI_ENDORSEMENT_CLAIM_ALLOWED" in payload["missing"]

def test_autonomous_delegation_requires_machine_mediated_authority_ready():
    ok, missing = validate_autonomous_delegation_ready(CASE_ID)
    assert ok is False
    assert "MACHINE_MEDIATED_AUTHORITY_READY_REQUIRED_FOR_AUTONOMOUS_DELEGATION" in missing
    assert any(item.startswith("MACHINE_MEDIATED_AUTHORITY::") for item in missing)
    assert "AUTONOMOUS_DELEGATION_READINESS_ACCEPTED" in missing
    assert "AUTONOMOUS_DELEGATION_ALLOWED" in missing
    assert "DELEGATED_EXECUTION_ALLOWED" in missing
    assert "AGENTIC_ROUTING_ALLOWED" in missing
    assert "AUTOMATED_GOVERNANCE_ACTION_ALLOWED" in missing
    assert "MACHINE_INITIATED_PUBLICATION_ALLOWED" in missing
    assert "AUTONOMOUS_CLAIM_PROPAGATION_ALLOWED" in missing
    assert "SELF_EXECUTING_AUTHORITY_ALLOWED" in missing


def test_cli_autonomous_delegation_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "autonomous-delegation-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["autonomous_delegation_ready"] is False
    assert "MACHINE_MEDIATED_AUTHORITY_READY_REQUIRED_FOR_AUTONOMOUS_DELEGATION" in payload["missing"]
    assert "AUTONOMOUS_DELEGATION_READINESS_ACCEPTED" in payload["missing"]
    assert "SELF_EXECUTING_AUTHORITY_ALLOWED" in payload["missing"]

def test_external_execution_requires_autonomous_delegation_ready():
    ok, missing = validate_external_execution_ready(CASE_ID)
    assert ok is False
    assert "AUTONOMOUS_DELEGATION_READY_REQUIRED_FOR_EXTERNAL_EXECUTION" in missing
    assert any(item.startswith("AUTONOMOUS_DELEGATION::") for item in missing)
    assert "EXTERNAL_EXECUTION_READINESS_ACCEPTED" in missing
    assert "EXTERNAL_EXECUTION_ALLOWED" in missing
    assert "REPOSITORY_MUTATION_ALLOWED" in missing
    assert "INFRASTRUCTURE_MUTATION_ALLOWED" in missing
    assert "THIRD_PARTY_API_EXECUTION_ALLOWED" in missing
    assert "OPERATIONAL_COMMAND_DISPATCH_ALLOWED" in missing
    assert "LEGAL_FINANCIAL_INSTRUCTION_ALLOWED" in missing
    assert "EXTERNAL_SYSTEM_SIDE_EFFECT_ALLOWED" in missing
    assert "IRREVERSIBLE_WORLD_ACTION_ALLOWED" in missing


def test_cli_external_execution_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "external-execution-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["external_execution_ready"] is False
    assert "AUTONOMOUS_DELEGATION_READY_REQUIRED_FOR_EXTERNAL_EXECUTION" in payload["missing"]
    assert "EXTERNAL_EXECUTION_READINESS_ACCEPTED" in payload["missing"]
    assert "IRREVERSIBLE_WORLD_ACTION_ALLOWED" in payload["missing"]

def test_credential_custody_requires_external_execution_ready():
    ok, missing = validate_credential_custody_ready(CASE_ID)
    assert ok is False
    assert "EXTERNAL_EXECUTION_READY_REQUIRED_FOR_CREDENTIAL_CUSTODY" in missing
    assert any(item.startswith("EXTERNAL_EXECUTION::") for item in missing)
    assert "CREDENTIAL_CUSTODY_READINESS_ACCEPTED" in missing
    assert "CREDENTIAL_CUSTODY_ALLOWED" in missing
    assert "SIGNING_KEY_USE_ALLOWED" in missing
    assert "DEPLOY_KEY_USE_ALLOWED" in missing
    assert "SECRET_MATERIAL_ACCESS_ALLOWED" in missing
    assert "ADMIN_TOKEN_USE_ALLOWED" in missing
    assert "PRODUCTION_WRITE_CREDENTIAL_ALLOWED" in missing
    assert "RELEASE_NOTARIZATION_ALLOWED" in missing
    assert "CUSTODY_BEARING_AUTOMATION_ALLOWED" in missing


def test_cli_credential_custody_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "credential-custody-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["credential_custody_ready"] is False
    assert "EXTERNAL_EXECUTION_READY_REQUIRED_FOR_CREDENTIAL_CUSTODY" in payload["missing"]
    assert "CREDENTIAL_CUSTODY_READINESS_ACCEPTED" in payload["missing"]
    assert "CUSTODY_BEARING_AUTOMATION_ALLOWED" in payload["missing"]

