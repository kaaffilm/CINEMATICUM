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
from cinematicum_studio.issuance_bridge.validate_execution_provenance import validate_execution_provenance_ready
from cinematicum_studio.issuance_bridge.validate_change_control import validate_change_control_ready
from cinematicum_studio.issuance_bridge.validate_deployment_authorization import validate_deployment_authorization_ready
from cinematicum_studio.issuance_bridge.validate_runtime_operation import validate_runtime_operation_ready
from cinematicum_studio.issuance_bridge.validate_observability import validate_observability_ready
from cinematicum_studio.issuance_bridge.validate_incident_response import validate_incident_response_ready
from cinematicum_studio.issuance_bridge.validate_service_recovery import validate_service_recovery_ready
from cinematicum_studio.issuance_bridge.validate_recovery_verification import validate_recovery_verification_ready


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

def test_execution_provenance_requires_credential_custody_ready():
    ok, missing = validate_execution_provenance_ready(CASE_ID)
    assert ok is False
    assert "CREDENTIAL_CUSTODY_READY_REQUIRED_FOR_EXECUTION_PROVENANCE" in missing
    assert any(item.startswith("CREDENTIAL_CUSTODY::") for item in missing)
    assert "EXECUTION_PROVENANCE_READINESS_ACCEPTED" in missing
    assert "EXECUTION_PROVENANCE_ALLOWED" in missing
    assert "SIGNED_EXECUTION_RECEIPT_ALLOWED" in missing
    assert "TAMPER_EVIDENT_AUDIT_LOG_ALLOWED" in missing
    assert "CUSTODY_CHAIN_ATTESTATION_ALLOWED" in missing
    assert "REPLAY_RESISTANT_OPERATION_RECORD_ALLOWED" in missing
    assert "NONREPUDIATION_CLAIM_ALLOWED" in missing
    assert "COMPLIANCE_EVIDENCE_EXPORT_ALLOWED" in missing
    assert "INCIDENT_RECONSTRUCTION_ALLOWED" in missing


def test_cli_execution_provenance_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "execution-provenance-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["execution_provenance_ready"] is False
    assert "CREDENTIAL_CUSTODY_READY_REQUIRED_FOR_EXECUTION_PROVENANCE" in payload["missing"]
    assert "EXECUTION_PROVENANCE_READINESS_ACCEPTED" in payload["missing"]
    assert "INCIDENT_RECONSTRUCTION_ALLOWED" in payload["missing"]

def test_change_control_requires_execution_provenance_ready():
    ok, missing = validate_change_control_ready(CASE_ID)
    assert ok is False
    assert "EXECUTION_PROVENANCE_READY_REQUIRED_FOR_CHANGE_CONTROL" in missing
    assert any(item.startswith("EXECUTION_PROVENANCE::") for item in missing)
    assert "CHANGE_CONTROL_READINESS_ACCEPTED" in missing
    assert "CHANGE_CONTROL_ALLOWED" in missing
    assert "APPROVED_CHANGE_REQUEST_ALLOWED" in missing
    assert "INDEPENDENT_REVIEW_ALLOWED" in missing
    assert "SEPARATION_OF_DUTIES_ALLOWED" in missing
    assert "ROLLBACK_PLAN_ALLOWED" in missing
    assert "BLAST_RADIUS_ASSESSMENT_ALLOWED" in missing
    assert "EMERGENCY_CHANGE_OVERRIDE_ALLOWED" in missing
    assert "POST_EXECUTION_ATTESTATION_ALLOWED" in missing


def test_cli_change_control_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "change-control-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["change_control_ready"] is False
    assert "EXECUTION_PROVENANCE_READY_REQUIRED_FOR_CHANGE_CONTROL" in payload["missing"]
    assert "CHANGE_CONTROL_READINESS_ACCEPTED" in payload["missing"]
    assert "POST_EXECUTION_ATTESTATION_ALLOWED" in payload["missing"]

def test_deployment_authorization_requires_change_control_ready():
    ok, missing = validate_deployment_authorization_ready(CASE_ID)
    assert ok is False
    assert "CHANGE_CONTROL_READY_REQUIRED_FOR_DEPLOYMENT_AUTHORIZATION" in missing
    assert any(item.startswith("CHANGE_CONTROL::") for item in missing)
    assert "DEPLOYMENT_AUTHORIZATION_READINESS_ACCEPTED" in missing
    assert "DEPLOYMENT_AUTHORIZATION_ALLOWED" in missing
    assert "RELEASE_PROMOTION_ALLOWED" in missing
    assert "PRODUCTION_DEPLOYMENT_ALLOWED" in missing
    assert "ENVIRONMENT_TARGETING_ALLOWED" in missing
    assert "DEPLOYMENT_WINDOW_ALLOWED" in missing
    assert "OPERATOR_ASSIGNMENT_ALLOWED" in missing
    assert "DEPLOYMENT_LOCK_RELEASE_ALLOWED" in missing
    assert "ROLLBACK_EXECUTION_ALLOWED" in missing


def test_cli_deployment_authorization_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "deployment-authorization-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["deployment_authorization_ready"] is False
    assert "CHANGE_CONTROL_READY_REQUIRED_FOR_DEPLOYMENT_AUTHORIZATION" in payload["missing"]
    assert "DEPLOYMENT_AUTHORIZATION_READINESS_ACCEPTED" in payload["missing"]
    assert "ROLLBACK_EXECUTION_ALLOWED" in payload["missing"]

def test_runtime_operation_requires_deployment_authorization_ready():
    ok, missing = validate_runtime_operation_ready(CASE_ID)
    assert ok is False
    assert "DEPLOYMENT_AUTHORIZATION_READY_REQUIRED_FOR_RUNTIME_OPERATION" in missing
    assert any(item.startswith("DEPLOYMENT_AUTHORIZATION::") for item in missing)
    assert "RUNTIME_OPERATION_READINESS_ACCEPTED" in missing
    assert "RUNTIME_OPERATION_ALLOWED" in missing
    assert "PRODUCTION_RUNTIME_ACTIVATION_ALLOWED" in missing
    assert "LIVE_TRAFFIC_EXPOSURE_ALLOWED" in missing
    assert "SERVICE_ACCOUNT_ACTIVATION_ALLOWED" in missing
    assert "SCHEDULER_ACTIVATION_ALLOWED" in missing
    assert "TELEMETRY_EMISSION_ALLOWED" in missing
    assert "ALERT_ROUTING_ALLOWED" in missing
    assert "OPERATIONAL_ROLLBACK_ALLOWED" in missing
    assert "EXTERNAL_INVOCATION_ALLOWED" in missing


def test_cli_runtime_operation_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "runtime-operation-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["runtime_operation_ready"] is False
    assert "DEPLOYMENT_AUTHORIZATION_READY_REQUIRED_FOR_RUNTIME_OPERATION" in payload["missing"]
    assert "RUNTIME_OPERATION_READINESS_ACCEPTED" in payload["missing"]
    assert "EXTERNAL_INVOCATION_ALLOWED" in payload["missing"]

def test_observability_requires_runtime_operation_ready():
    ok, missing = validate_observability_ready(CASE_ID)
    assert ok is False
    assert "RUNTIME_OPERATION_READY_REQUIRED_FOR_OBSERVABILITY" in missing
    assert any(item.startswith("RUNTIME_OPERATION::") for item in missing)
    assert "OBSERVABILITY_READINESS_ACCEPTED" in missing
    assert "OBSERVABILITY_ALLOWED" in missing
    assert "HEALTH_STATUS_CLAIM_ALLOWED" in missing
    assert "TELEMETRY_INTERPRETATION_ALLOWED" in missing
    assert "ALERT_EVALUATION_ALLOWED" in missing
    assert "SLO_EVALUATION_ALLOWED" in missing
    assert "INCIDENT_SIGNAL_ALLOWED" in missing
    assert "DASHBOARD_PUBLICATION_ALLOWED" in missing
    assert "LOG_CORRELATION_ALLOWED" in missing
    assert "METRIC_EXPORT_ALLOWED" in missing
    assert "TRACE_ANALYSIS_ALLOWED" in missing


def test_cli_observability_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "observability-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["observability_ready"] is False
    assert "RUNTIME_OPERATION_READY_REQUIRED_FOR_OBSERVABILITY" in payload["missing"]
    assert "OBSERVABILITY_READINESS_ACCEPTED" in payload["missing"]
    assert "TRACE_ANALYSIS_ALLOWED" in payload["missing"]

def test_incident_response_requires_observability_ready():
    ok, missing = validate_incident_response_ready(CASE_ID)
    assert ok is False
    assert "OBSERVABILITY_READY_REQUIRED_FOR_INCIDENT_RESPONSE" in missing
    assert any(item.startswith("OBSERVABILITY::") for item in missing)
    assert "INCIDENT_RESPONSE_READINESS_ACCEPTED" in missing
    assert "INCIDENT_RESPONSE_ALLOWED" in missing
    assert "INCIDENT_DECLARATION_ALLOWED" in missing
    assert "PAGING_ALLOWED" in missing
    assert "ESCALATION_ALLOWED" in missing
    assert "INCIDENT_COMMANDER_ASSIGNMENT_ALLOWED" in missing
    assert "MITIGATION_ACTION_ALLOWED" in missing
    assert "CONTAINMENT_ACTION_ALLOWED" in missing
    assert "REMEDIATION_ACTION_ALLOWED" in missing
    assert "STATUS_PAGE_UPDATE_ALLOWED" in missing
    assert "CUSTOMER_NOTIFICATION_ALLOWED" in missing
    assert "POSTMORTEM_RECORD_ALLOWED" in missing


def test_cli_incident_response_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "incident-response-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["incident_response_ready"] is False
    assert "OBSERVABILITY_READY_REQUIRED_FOR_INCIDENT_RESPONSE" in payload["missing"]
    assert "INCIDENT_RESPONSE_READINESS_ACCEPTED" in payload["missing"]
    assert "POSTMORTEM_RECORD_ALLOWED" in payload["missing"]

def test_service_recovery_requires_incident_response_ready():
    ok, missing = validate_service_recovery_ready(CASE_ID)
    assert ok is False
    assert "INCIDENT_RESPONSE_READY_REQUIRED_FOR_SERVICE_RECOVERY" in missing
    assert any(item.startswith("INCIDENT_RESPONSE::") for item in missing)
    assert "SERVICE_RECOVERY_READINESS_ACCEPTED" in missing
    assert "SERVICE_RECOVERY_ALLOWED" in missing
    assert "RECOVERY_EXECUTION_ALLOWED" in missing
    assert "FAILOVER_ALLOWED" in missing
    assert "TRAFFIC_RESTORATION_ALLOWED" in missing
    assert "ROLLBACK_COMPLETION_ALLOWED" in missing
    assert "DATA_REPAIR_ALLOWED" in missing
    assert "REPLAY_EXECUTION_ALLOWED" in missing
    assert "PERMANENT_FIX_CLAIM_ALLOWED" in missing
    assert "INCIDENT_CLOSURE_ALLOWED" in missing
    assert "RESOLVED_STATUS_CLAIM_ALLOWED" in missing
    assert "CUSTOMER_RESTORATION_NOTICE_ALLOWED" in missing


def test_cli_service_recovery_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "service-recovery-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["service_recovery_ready"] is False
    assert "INCIDENT_RESPONSE_READY_REQUIRED_FOR_SERVICE_RECOVERY" in payload["missing"]
    assert "SERVICE_RECOVERY_READINESS_ACCEPTED" in payload["missing"]
    assert "RESOLVED_STATUS_CLAIM_ALLOWED" in payload["missing"]

def test_recovery_verification_requires_service_recovery_ready():
    ok, missing = validate_recovery_verification_ready(CASE_ID)
    assert ok is False
    assert "SERVICE_RECOVERY_READY_REQUIRED_FOR_RECOVERY_VERIFICATION" in missing
    assert any(item.startswith("SERVICE_RECOVERY::") for item in missing)
    assert "RECOVERY_VERIFICATION_READINESS_ACCEPTED" in missing
    assert "RECOVERY_VERIFICATION_ALLOWED" in missing
    assert "POST_RECOVERY_HEALTH_VERIFICATION_ALLOWED" in missing
    assert "TRAFFIC_STABILITY_VERIFICATION_ALLOWED" in missing
    assert "DATA_INTEGRITY_VERIFICATION_ALLOWED" in missing
    assert "ROLLBACK_VERIFICATION_ALLOWED" in missing
    assert "REPLAY_COMPLETENESS_VERIFICATION_ALLOWED" in missing
    assert "CUSTOMER_IMPACT_END_CLAIM_ALLOWED" in missing
    assert "MONITORING_STABILITY_CLAIM_ALLOWED" in missing
    assert "NORMAL_OPERATIONS_RESTORED_CLAIM_ALLOWED" in missing
    assert "INCIDENT_DEESCALATION_ALLOWED" in missing
    assert "RECOVERY_SUCCESS_CLAIM_ALLOWED" in missing


def test_cli_recovery_verification_command_executes():
    result = subprocess.run(
        [sys.executable, "-m", "cinematicum_studio.cli", "recovery-verification-check", CASE_ID],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["recovery_verification_ready"] is False
    assert "SERVICE_RECOVERY_READY_REQUIRED_FOR_RECOVERY_VERIFICATION" in payload["missing"]
    assert "RECOVERY_VERIFICATION_READINESS_ACCEPTED" in payload["missing"]
    assert "NORMAL_OPERATIONS_RESTORED_CLAIM_ALLOWED" in payload["missing"]


def test_missing_local_render_proof_boundary_fails_closed():
    film_dir = ROOT / "CASES" / CASE_ID / "FILM"
    proof_path = film_dir / "LOCAL_RENDER_PROOF_CLASSIFICATION.json"
    backup = proof_path.read_text() if proof_path.exists() else None

    try:
        if proof_path.exists():
            proof_path.unlink()

        ok, missing = validate_admissible_motion_picture(CASE_ID)

        assert ok is False
        assert "LOCAL_RENDER_PROOF_CLASSIFICATION.json" in missing
    finally:
        if backup is not None:
            proof_path.write_text(backup)

def test_non_admissible_render_artifact_in_take_ledger_is_not_admissible_film(tmp_path):
    film_dir = ROOT / "CASES" / CASE_ID / "FILM"
    ledger_path = film_dir / "TAKE_LEDGER.json"
    backup = ledger_path.read_text()

    try:
        ledger_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "shots": [{
                "shot_id": "SHOT_001",
                "takes": [{
                    "id": "SHOT_001_TAKE_001",
                    "case_id": CASE_ID,
                    "shot_id": "SHOT_001",
                    "backend": "mock-render-backend",
                    "model": "synthetic-placeholder-render-generator",
                    "file_path": ".cinematicum_media/CASE_001_THE_LAST_RENDER/generated/SHOT_001/TAKE_001.mp4",
                    "status": "GENERATED"
                }]
            }]
        }, indent=2) + "\n")

        ok, missing = validate_admissible_motion_picture(CASE_ID)

        assert ok is False
        assert "NON_ADMISSIBLE_RENDER_ARTIFACT_NOT_FILM" in missing
    finally:
        ledger_path.write_text(backup)

def test_take_ledger_without_explicit_source_admissibility_fails_closed():
    ok, missing = validate_admissible_motion_picture(CASE_ID)

    assert ok is False
    assert "TAKE_LEDGER_SOURCE_ADMISSIBILITY_UNPROVEN" in missing

def test_take_source_admissibility_requires_external_evidence_record():
    film_dir = ROOT / "CASES" / CASE_ID / "FILM"
    ledger_path = film_dir / "TAKE_LEDGER.json"
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"

    ledger_backup = ledger_path.read_text()
    evidence_backup = evidence_path.read_text() if evidence_path.exists() else None

    try:
        ledger_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "shots": [
                {
                    "shot_id": "SHOT_001",
                    "takes": [
                        {
                            "id": "SHOT_001_TAKE_001",
                            "shot_id": "SHOT_001",
                            "file_path": "external/final/source.mov",
                            "sha256": "0" * 64,
                            "is_admissible_film_source": True,
                            "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                        }
                    ],
                }
            ],
        }, indent=2) + "\n")

        if evidence_path.exists():
            evidence_path.unlink()

        ok, missing = validate_admissible_motion_picture(CASE_ID)

        assert ok is False
        assert "TAKE_SOURCE_ADMISSIBILITY_EVIDENCE_MISSING" in missing
    finally:
        ledger_path.write_text(ledger_backup)
        if evidence_backup is not None:
            evidence_path.write_text(evidence_backup)
        elif evidence_path.exists():
            evidence_path.unlink()

def test_take_source_admissibility_evidence_requires_bound_payload():
    film_dir = ROOT / "CASES" / CASE_ID / "FILM"
    ledger_path = film_dir / "TAKE_LEDGER.json"
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"

    ledger_backup = ledger_path.read_text()
    evidence_backup = evidence_path.read_text() if evidence_path.exists() else None

    try:
        ledger_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "shots": [
                {
                    "shot_id": "SHOT_001",
                    "takes": [
                        {
                            "id": "SHOT_001_TAKE_001",
                            "shot_id": "SHOT_001",
                            "file_path": "external/final/source.mov",
                            "sha256": "1" * 64,
                            "is_admissible_film_source": True,
                            "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                        }
                    ],
                }
            ],
        }, indent=2) + "\n")

        evidence_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "admissible_sources": [
                {
                    "take_id": "SHOT_001_TAKE_001",
                    "sha256": "1" * 64,
                    "admissibility_evidence_accepted": True,
                    "evidence_file_path": str(film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE" / "missing.json"),
                    "evidence_sha256": "2" * 64,
                }
            ],
        }, indent=2) + "\n")

        ok, missing = validate_admissible_motion_picture(CASE_ID)

        assert ok is False
        assert "TAKE_SOURCE_ADMISSIBILITY_EVIDENCE_PAYLOAD_INVALID" in missing
    finally:
        ledger_path.write_text(ledger_backup)
        if evidence_backup is not None:
            evidence_path.write_text(evidence_backup)
        elif evidence_path.exists():
            evidence_path.unlink()

def test_take_source_admissibility_evidence_payload_cannot_self_attest():
    import hashlib

    film_dir = ROOT / "CASES" / CASE_ID / "FILM"
    ledger_path = film_dir / "TAKE_LEDGER.json"
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    payload_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    payload_path = payload_dir / "SHOT_001_TAKE_001.self_attested.json"

    ledger_backup = ledger_path.read_text()
    evidence_backup = evidence_path.read_text() if evidence_path.exists() else None
    payload_backup = payload_path.read_text() if payload_path.exists() else None

    try:
        payload_dir.mkdir(exist_ok=True)

        ledger_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "shots": [
                {
                    "shot_id": "SHOT_001",
                    "takes": [
                        {
                            "id": "SHOT_001_TAKE_001",
                            "shot_id": "SHOT_001",
                            "file_path": "external/final/source.mov",
                            "sha256": "1" * 64,
                            "is_admissible_film_source": True,
                            "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                        }
                    ],
                }
            ],
        }, indent=2) + "\n")

        payload_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_EVIDENCE",
            "case_id": CASE_ID,
            "take_id": "SHOT_001_TAKE_001",
            "source_sha256": "1" * 64,
            "accepted": True,
            "evidence_verdict": "ADMISSIBLE_FINAL_FILM_SOURCE",
            "self_attested": True,
            "authority_classification": "SELF_ATTESTED_SOURCE_ADMISSIBILITY",
        }, indent=2) + "\n")

        payload_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest()

        evidence_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "admissible_sources": [
                {
                    "take_id": "SHOT_001_TAKE_001",
                    "sha256": "1" * 64,
                    "admissibility_evidence_accepted": True,
                    "evidence_file_path": str(payload_path.relative_to(ROOT)),
                    "evidence_sha256": payload_sha256,
                }
            ],
        }, indent=2) + "\n")

        ok, missing = validate_admissible_motion_picture(CASE_ID)

        assert ok is False
        assert "TAKE_SOURCE_ADMISSIBILITY_EVIDENCE_PAYLOAD_UNBOUND" in missing
    finally:
        ledger_path.write_text(ledger_backup)
        if evidence_backup is not None:
            evidence_path.write_text(evidence_backup)
        elif evidence_path.exists():
            evidence_path.unlink()

        if payload_backup is not None:
            payload_path.write_text(payload_backup)
        elif payload_path.exists():
            payload_path.unlink()

def test_take_source_admissibility_requires_bound_independent_authority_record():
    import hashlib

    film_dir = ROOT / "CASES" / CASE_ID / "FILM"
    ledger_path = film_dir / "TAKE_LEDGER.json"
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    payload_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    payload_path = payload_dir / "SHOT_001_TAKE_001.independent.json"

    ledger_backup = ledger_path.read_text()
    evidence_backup = evidence_path.read_text() if evidence_path.exists() else None
    payload_backup = payload_path.read_text() if payload_path.exists() else None

    try:
        payload_dir.mkdir(exist_ok=True)

        ledger_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "shots": [
                {
                    "shot_id": "SHOT_001",
                    "takes": [
                        {
                            "id": "SHOT_001_TAKE_001",
                            "shot_id": "SHOT_001",
                            "file_path": "external/final/source.mov",
                            "sha256": "1" * 64,
                            "is_admissible_film_source": True,
                            "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                        }
                    ],
                }
            ],
        }, indent=2) + "\n")

        payload_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_EVIDENCE",
            "case_id": CASE_ID,
            "take_id": "SHOT_001_TAKE_001",
            "source_sha256": "1" * 64,
            "accepted": True,
            "evidence_verdict": "ADMISSIBLE_FINAL_FILM_SOURCE",
            "self_attested": False,
            "authority_classification": "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY",
        }, indent=2) + "\n")

        payload_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest()

        evidence_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "admissible_sources": [
                {
                    "take_id": "SHOT_001_TAKE_001",
                    "sha256": "1" * 64,
                    "admissibility_evidence_accepted": True,
                    "evidence_file_path": str(payload_path.relative_to(ROOT)),
                    "evidence_sha256": payload_sha256
                }
            ],
        }, indent=2) + "\n")

        ok, missing = validate_admissible_motion_picture(CASE_ID)

        assert ok is False
        assert "TAKE_SOURCE_ADMISSIBILITY_AUTHORITY_UNBOUND" in missing
    finally:
        ledger_path.write_text(ledger_backup)

        if evidence_backup is None:
            evidence_path.unlink(missing_ok=True)
        else:
            evidence_path.write_text(evidence_backup)

        if payload_backup is None:
            payload_path.unlink(missing_ok=True)
        else:
            payload_path.write_text(payload_backup)

def test_take_source_admissibility_authority_must_bind_exact_source_tuple():
    import hashlib

    film_dir = ROOT / "CASES" / CASE_ID / "FILM"
    ledger_path = film_dir / "TAKE_LEDGER.json"
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    payload_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    payload_path = payload_dir / "SHOT_001_TAKE_001.bound_payload.json"
    authority_path = payload_dir / "SOURCE_AUTHORITY_001.json"

    ledger_backup = ledger_path.read_text()
    evidence_backup = evidence_path.read_text() if evidence_path.exists() else None
    payload_backup = payload_path.read_text() if payload_path.exists() else None
    authority_backup = authority_path.read_text() if authority_path.exists() else None

    try:
        payload_dir.mkdir(exist_ok=True)

        ledger_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "shots": [
                {
                    "shot_id": "SHOT_001",
                    "takes": [
                        {
                            "id": "SHOT_001_TAKE_001",
                            "shot_id": "SHOT_001",
                            "file_path": "external/final/source.mov",
                            "sha256": "1" * 64,
                            "is_admissible_film_source": True,
                            "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                        }
                    ],
                }
            ],
        }, indent=2) + "\n")

        payload_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_EVIDENCE",
            "case_id": CASE_ID,
            "take_id": "SHOT_001_TAKE_001",
            "source_sha256": "1" * 64,
            "accepted": True,
            "evidence_verdict": "ADMISSIBLE_FINAL_FILM_SOURCE",
            "self_attested": False,
            "authority_classification": "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY",
        }, indent=2) + "\n")

        payload_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest()

        authority_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_AUTHORITY",
            "case_id": CASE_ID,
            "authority_id": "SOURCE_AUTHORITY_001",
            "authority_classification": "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY",
            "self_attested": False,
            "may_certify_source_admissibility": True,
            "certified_sources": []
        }, indent=2) + "\n")

        authority_sha256 = hashlib.sha256(authority_path.read_bytes()).hexdigest()

        evidence_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "admissible_sources": [
                {
                    "take_id": "SHOT_001_TAKE_001",
                    "sha256": "1" * 64,
                    "admissibility_evidence_accepted": True,
                    "evidence_file_path": str(payload_path.relative_to(ROOT)),
                    "evidence_sha256": payload_sha256,
                    "authority_id": "SOURCE_AUTHORITY_001",
                    "authority_record_path": str(authority_path.relative_to(ROOT)),
                    "authority_record_sha256": authority_sha256,
                }
            ],
        }, indent=2) + "\n")

        ok, missing = validate_admissible_motion_picture(CASE_ID)

        assert ok is False
        assert "TAKE_SOURCE_ADMISSIBILITY_AUTHORITY_SOURCE_UNBOUND" in missing
    finally:
        ledger_path.write_text(ledger_backup)

        if evidence_backup is None:
            evidence_path.unlink(missing_ok=True)
        else:
            evidence_path.write_text(evidence_backup)

        if payload_backup is None:
            payload_path.unlink(missing_ok=True)
        else:
            payload_path.write_text(payload_backup)

        if authority_backup is None:
            authority_path.unlink(missing_ok=True)
        else:
            authority_path.write_text(authority_backup)

def test_take_source_admissibility_payload_must_bind_certifying_authority():
    import hashlib

    film_dir = ROOT / "CASES" / CASE_ID / "FILM"
    ledger_path = film_dir / "TAKE_LEDGER.json"
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    payload_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    payload_path = payload_dir / "SHOT_001_TAKE_001.payload_without_authority.json"
    authority_path = payload_dir / "SOURCE_AUTHORITY_001.payload_binding.json"

    ledger_backup = ledger_path.read_text()
    evidence_backup = evidence_path.read_text() if evidence_path.exists() else None
    payload_backup = payload_path.read_text() if payload_path.exists() else None
    authority_backup = authority_path.read_text() if authority_path.exists() else None

    try:
        payload_dir.mkdir(exist_ok=True)

        ledger_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "shots": [
                {
                    "shot_id": "SHOT_001",
                    "takes": [
                        {
                            "id": "SHOT_001_TAKE_001",
                            "shot_id": "SHOT_001",
                            "file_path": "external/final/source.mov",
                            "sha256": "1" * 64,
                            "is_admissible_film_source": True,
                            "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                        }
                    ],
                }
            ],
        }, indent=2) + "\n")

        payload_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_EVIDENCE",
            "case_id": CASE_ID,
            "take_id": "SHOT_001_TAKE_001",
            "source_sha256": "1" * 64,
            "accepted": True,
            "evidence_verdict": "ADMISSIBLE_FINAL_FILM_SOURCE",
            "self_attested": False,
            "authority_classification": "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY",
        }, indent=2) + "\n")

        payload_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest()

        authority_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_AUTHORITY",
            "case_id": CASE_ID,
            "authority_id": "SOURCE_AUTHORITY_001",
            "authority_classification": "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY",
            "self_attested": False,
            "may_certify_source_admissibility": True,
            "certified_sources": [
                {
                    "authority_id": "SOURCE_AUTHORITY_001",
                    "take_id": "SHOT_001_TAKE_001",
                    "source_sha256": "1" * 64,
                    "evidence_sha256": payload_sha256,
                    "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                }
            ],
        }, indent=2) + "\n")

        authority_sha256 = hashlib.sha256(authority_path.read_bytes()).hexdigest()

        evidence_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "admissible_sources": [
                {
                    "take_id": "SHOT_001_TAKE_001",
                    "sha256": "1" * 64,
                    "admissibility_evidence_accepted": True,
                    "evidence_file_path": str(payload_path.relative_to(ROOT)),
                    "evidence_sha256": payload_sha256,
                    "authority_id": "SOURCE_AUTHORITY_001",
                    "authority_record_path": str(authority_path.relative_to(ROOT)),
                    "authority_record_sha256": authority_sha256,
                }
            ],
        }, indent=2) + "\n")

        ok, missing = validate_admissible_motion_picture(CASE_ID)

        assert ok is False
        assert "TAKE_SOURCE_ADMISSIBILITY_EVIDENCE_PAYLOAD_AUTHORITY_UNBOUND" in missing
    finally:
        ledger_path.write_text(ledger_backup)

        if evidence_backup is None:
            evidence_path.unlink(missing_ok=True)
        else:
            evidence_path.write_text(evidence_backup)

        if payload_backup is None:
            payload_path.unlink(missing_ok=True)
        else:
            payload_path.write_text(payload_backup)

        if authority_backup is None:
            authority_path.unlink(missing_ok=True)
        else:
            authority_path.write_text(authority_backup)

def test_take_source_admissibility_authority_requires_bound_grant():
    import hashlib

    film_dir = ROOT / "CASES" / CASE_ID / "FILM"
    ledger_path = film_dir / "TAKE_LEDGER.json"
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    payload_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    payload_path = payload_dir / "SHOT_001_TAKE_001.payload_with_authority.json"
    authority_path = payload_dir / "SOURCE_AUTHORITY_001.ungranted.json"

    ledger_backup = ledger_path.read_text()
    evidence_backup = evidence_path.read_text() if evidence_path.exists() else None
    payload_backup = payload_path.read_text() if payload_path.exists() else None
    authority_backup = authority_path.read_text() if authority_path.exists() else None

    try:
        payload_dir.mkdir(exist_ok=True)

        ledger_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "shots": [
                {
                    "shot_id": "SHOT_001",
                    "takes": [
                        {
                            "id": "SHOT_001_TAKE_001",
                            "shot_id": "SHOT_001",
                            "file_path": "external/final/source.mov",
                            "sha256": "1" * 64,
                            "is_admissible_film_source": True,
                            "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                        }
                    ],
                }
            ],
        }, indent=2) + "\n")

        authority_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_AUTHORITY",
            "case_id": CASE_ID,
            "authority_id": "SOURCE_AUTHORITY_001",
            "authority_classification": "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY",
            "self_attested": False,
            "may_certify_source_admissibility": True,
            "certified_sources": [
                {
                    "authority_id": "SOURCE_AUTHORITY_001",
                    "take_id": "SHOT_001_TAKE_001",
                    "source_sha256": "1" * 64,
                    "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                }
            ],
        }, indent=2) + "\n")

        authority_sha256 = hashlib.sha256(authority_path.read_bytes()).hexdigest()

        payload_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_EVIDENCE",
            "case_id": CASE_ID,
            "take_id": "SHOT_001_TAKE_001",
            "source_sha256": "1" * 64,
            "accepted": True,
            "evidence_verdict": "ADMISSIBLE_FINAL_FILM_SOURCE",
            "self_attested": False,
            "authority_classification": "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY",
            "authority_id": "SOURCE_AUTHORITY_001",
            "authority_record_path": str(authority_path.relative_to(ROOT)),
            "authority_record_sha256": authority_sha256,
        }, indent=2) + "\n")

        payload_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest()

        authority = json.loads(authority_path.read_text())
        authority["certified_sources"][0]["evidence_sha256"] = payload_sha256
        authority_path.write_text(json.dumps(authority, indent=2) + "\n")
        authority_sha256 = hashlib.sha256(authority_path.read_bytes()).hexdigest()

        payload = json.loads(payload_path.read_text())
        payload["authority_record_sha256"] = authority_sha256
        payload_path.write_text(json.dumps(payload, indent=2) + "\n")
        payload_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest()

        evidence_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "admissible_sources": [
                {
                    "case_id": CASE_ID,
                    "take_id": "SHOT_001_TAKE_001",
                    "sha256": "1" * 64,
                    "admissibility_evidence_accepted": True,
                    "evidence_file_path": str(payload_path.relative_to(ROOT)),
                    "evidence_sha256": payload_sha256,
                    "authority_id": "SOURCE_AUTHORITY_001",
                    "authority_record_path": str(authority_path.relative_to(ROOT)),
                    "authority_record_sha256": authority_sha256,
                }
            ],
        }, indent=2) + "\n")

        ok, missing = validate_admissible_motion_picture(CASE_ID)

        assert ok is False
        assert "TAKE_SOURCE_ADMISSIBILITY_AUTHORITY_GRANT_UNBOUND" in missing
    finally:
        ledger_path.write_text(ledger_backup)

        if evidence_backup is None:
            evidence_path.unlink(missing_ok=True)
        else:
            evidence_path.write_text(evidence_backup)

        if payload_backup is None:
            payload_path.unlink(missing_ok=True)
        else:
            payload_path.write_text(payload_backup)

        if authority_backup is None:
            authority_path.unlink(missing_ok=True)
        else:
            authority_path.write_text(authority_backup)

def test_take_source_admissibility_authority_grant_requires_bound_issuer():
    import hashlib

    film_dir = ROOT / "CASES" / CASE_ID / "FILM"
    ledger_path = film_dir / "TAKE_LEDGER.json"
    evidence_path = film_dir / "TAKE_SOURCE_ADMISSIBILITY_LEDGER.json"
    payload_dir = film_dir / "SOURCE_ADMISSIBILITY_EVIDENCE"
    payload_path = payload_dir / "SHOT_001_TAKE_001.payload_with_grant.json"
    authority_path = payload_dir / "SOURCE_AUTHORITY_001.with_grant.json"
    grant_path = payload_dir / "SOURCE_AUTHORITY_001.grant_without_issuer.json"

    ledger_backup = ledger_path.read_text()
    evidence_backup = evidence_path.read_text() if evidence_path.exists() else None
    payload_backup = payload_path.read_text() if payload_path.exists() else None
    authority_backup = authority_path.read_text() if authority_path.exists() else None
    grant_backup = grant_path.read_text() if grant_path.exists() else None

    try:
        payload_dir.mkdir(exist_ok=True)

        ledger_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "shots": [
                {
                    "shot_id": "SHOT_001",
                    "takes": [
                        {
                            "id": "SHOT_001_TAKE_001",
                            "shot_id": "SHOT_001",
                            "file_path": "external/final/source.mov",
                            "sha256": "1" * 64,
                            "is_admissible_film_source": True,
                            "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                        }
                    ],
                }
            ],
        }, indent=2) + "\n")

        authority_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_AUTHORITY",
            "case_id": CASE_ID,
            "authority_id": "SOURCE_AUTHORITY_001",
            "authority_classification": "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY",
            "self_attested": False,
            "may_certify_source_admissibility": True,
            "certified_sources": [
                {
                    "authority_id": "SOURCE_AUTHORITY_001",
                    "take_id": "SHOT_001_TAKE_001",
                    "source_sha256": "1" * 64,
                    "source_admissibility_classification": "ADMISSIBLE_FINAL_FILM_SOURCE",
                }
            ],
        }, indent=2) + "\n")

        authority_sha256 = hashlib.sha256(authority_path.read_bytes()).hexdigest()

        payload_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_EVIDENCE",
            "case_id": CASE_ID,
            "take_id": "SHOT_001_TAKE_001",
            "source_sha256": "1" * 64,
            "accepted": True,
            "evidence_verdict": "ADMISSIBLE_FINAL_FILM_SOURCE",
            "self_attested": False,
            "authority_classification": "INDEPENDENT_SOURCE_ADMISSIBILITY_AUTHORITY",
            "authority_id": "SOURCE_AUTHORITY_001",
            "authority_record_path": str(authority_path.relative_to(ROOT)),
            "authority_record_sha256": authority_sha256,
        }, indent=2) + "\n")

        payload_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest()

        grant_path.write_text(json.dumps({
            "object_type": "CINEMATICUM_TAKE_SOURCE_ADMISSIBILITY_AUTHORITY_GRANT",
            "case_id": CASE_ID,
            "grant_id": "SOURCE_AUTHORITY_GRANT_001",
            "authority_id": "SOURCE_AUTHORITY_001",
            "authority_record_path": str(authority_path.relative_to(ROOT)),
            "authority_record_sha256": authority_sha256,
            "grants_source_admissibility_authority": True,
            "scope": "TAKE_SOURCE_ADMISSIBILITY",
            "revoked": False,
        }, indent=2) + "\n")

        grant_sha256 = hashlib.sha256(grant_path.read_bytes()).hexdigest()

        authority = json.loads(authority_path.read_text())
        authority["authority_grant_id"] = "SOURCE_AUTHORITY_GRANT_001"
        authority["authority_grant_path"] = str(grant_path.relative_to(ROOT))
        authority["authority_grant_sha256"] = grant_sha256
        authority["certified_sources"][0]["evidence_sha256"] = payload_sha256
        authority_path.write_text(json.dumps(authority, indent=2) + "\n")
        authority_sha256 = hashlib.sha256(authority_path.read_bytes()).hexdigest()

        payload = json.loads(payload_path.read_text())
        payload["authority_record_sha256"] = authority_sha256
        payload_path.write_text(json.dumps(payload, indent=2) + "\n")
        payload_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest()

        evidence_path.write_text(json.dumps({
            "case_id": CASE_ID,
            "admissible_sources": [
                {
                    "case_id": CASE_ID,
                    "take_id": "SHOT_001_TAKE_001",
                    "sha256": "1" * 64,
                    "admissibility_evidence_accepted": True,
                    "evidence_file_path": str(payload_path.relative_to(ROOT)),
                    "evidence_sha256": payload_sha256,
                    "authority_id": "SOURCE_AUTHORITY_001",
                    "authority_record_path": str(authority_path.relative_to(ROOT)),
                    "authority_record_sha256": authority_sha256,
                }
            ],
        }, indent=2) + "\n")

        ok, missing = validate_admissible_motion_picture(CASE_ID)

        assert ok is False
        assert "TAKE_SOURCE_ADMISSIBILITY_AUTHORITY_GRANT_ISSUER_UNBOUND" in missing
    finally:
        ledger_path.write_text(ledger_backup)

        if evidence_backup is None:
            evidence_path.unlink(missing_ok=True)
        else:
            evidence_path.write_text(evidence_backup)

        if payload_backup is None:
            payload_path.unlink(missing_ok=True)
        else:
            payload_path.write_text(payload_backup)

        if authority_backup is None:
            authority_path.unlink(missing_ok=True)
        else:
            authority_path.write_text(authority_backup)

        if grant_backup is None:
            grant_path.unlink(missing_ok=True)
        else:
            grant_path.write_text(grant_backup)

