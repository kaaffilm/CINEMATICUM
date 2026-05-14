import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "CASES" / "CASE_001_THE_LAST_RENDER"

CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
NEXT_STATE = "RELEASE_CANDIDATE_READY"

EXECUTION_OBJECT = "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_EXECUTION_RECORD"
EXECUTION_ID = "EXEC_001_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT"


def load_json(path):
    with path.open() as f:
        return json.load(f)


class TestReleaseCandidateReadyStateAdvancementExecutionRecord(unittest.TestCase):
    def setUp(self):
        self.root_record_path = ROOT / "CINEMATICUM_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_EXECUTION_RECORD.json"
        self.law_path = ROOT / "CINEMATICUM_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_EXECUTION_RECORD_LAW.json"
        self.case_record_path = CASE / EXECUTION_OBJECT / f"{EXECUTION_ID}.json"
        self.status_path = CASE / f"{EXECUTION_OBJECT}_STATUS.json"

        self.decision_path = ROOT / "CINEMATICUM_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_DECISION_RECORD.json"
        self.request_path = ROOT / "CINEMATICUM_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST.json"

    def test_required_execution_record_files_exist(self):
        self.assertTrue(self.root_record_path.exists())
        self.assertTrue(self.law_path.exists())
        self.assertTrue(self.case_record_path.exists())
        self.assertTrue(self.status_path.exists())

    def test_execution_record_has_required_identity(self):
        record = load_json(self.root_record_path)

        self.assertEqual(record["current_state"], CURRENT_STATE)
        self.assertEqual(record["execution_object"], EXECUTION_OBJECT)
        self.assertEqual(record["execution_record_id"], EXECUTION_ID)
        self.assertEqual(record["requested_next_state"], NEXT_STATE)
        self.assertEqual(
            record["prior_decision_object"],
            "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_DECISION_RECORD",
        )
        self.assertEqual(
            record["request_object"],
            "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST",
        )

    def test_prior_request_and_decision_exist(self):
        self.assertTrue(self.request_path.exists())
        self.assertTrue(self.decision_path.exists())

        decision = load_json(self.decision_path)
        self.assertTrue(decision["decision_accepts_request"])
        self.assertTrue(decision["decision_authorizes_state_mutation"])
        self.assertTrue(decision["authority_satisfied_for_transition"])

    def test_execution_authorizes_next_index_object_without_mutating_index(self):
        record = load_json(self.root_record_path)

        self.assertTrue(record["state_mutation_execution_authorized"])
        self.assertTrue(record["current_state_index_mutation_authorized"])
        self.assertTrue(record["current_state_index_change_deferred_to_next_object"])
        self.assertTrue(record["current_state_index_still_points_to_from_state"])
        self.assertEqual(
            record["next_required_object"],
            "RELEASE_CANDIDATE_READY_CURRENT_STATE_INDEX_ADVANCEMENT_RECORD",
        )

        self.assertFalse(record["authority_satisfied"])
        self.assertFalse(record["may_advance_now"])
        self.assertFalse(record["release_candidate_ready"])
        self.assertFalse(record["issued"])
        self.assertFalse(record["media_present"])
        self.assertTrue(record["current_state_unchanged"])

    def test_law_forbids_inline_state_mutation(self):
        law = load_json(self.law_path)

        self.assertEqual(law["governs"], EXECUTION_OBJECT)
        self.assertTrue(law["sealed"])

        forbidden = set(law["forbids"])
        self.assertIn("CURRENT_STATE_INDEX_MUTATION_IN_THIS_OBJECT", forbidden)
        self.assertIn("RELEASE_CANDIDATE_READY_TRUE_IN_THIS_OBJECT", forbidden)
        self.assertIn("ISSUANCE_IN_THIS_OBJECT", forbidden)
        self.assertIn("MEDIA_ADMISSION_IN_THIS_OBJECT", forbidden)


if __name__ == "__main__":
    unittest.main()
