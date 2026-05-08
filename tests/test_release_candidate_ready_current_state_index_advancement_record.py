import json
import unittest
from pathlib import Path

CASE = "CASE_001_THE_LAST_RENDER"
FROM_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
TO_STATE = "RELEASE_CANDIDATE_READY"
OBJECT = "RELEASE_CANDIDATE_READY_CURRENT_STATE_INDEX_ADVANCEMENT_RECORD"
RECORD_ID = "ADV_001_RELEASE_CANDIDATE_READY_CURRENT_STATE_INDEX_ADVANCEMENT"

class TestReleaseCandidateReadyCurrentStateIndexAdvancementRecord(unittest.TestCase):
    def setUp(self):
        self.record_path = Path("CASES") / CASE / OBJECT / f"{RECORD_ID}.json"
        self.status_path = Path("CASES") / CASE / f"{OBJECT}_STATUS.json"
        self.root_path = Path("CINEMATICUM_RELEASE_CANDIDATE_READY_CURRENT_STATE_INDEX_ADVANCEMENT_RECORD.json")
        self.law_path = Path("CINEMATICUM_RELEASE_CANDIDATE_READY_CURRENT_STATE_INDEX_ADVANCEMENT_RECORD_LAW.json")
        self.record = json.loads(self.record_path.read_text())

    def test_required_files_exist(self):
        for path in [self.record_path, self.status_path, self.root_path, self.law_path]:
            self.assertTrue(path.exists(), str(path))

    def test_root_and_case_record_match(self):
        self.assertEqual(self.record, json.loads(self.root_path.read_text()))

    def test_record_identity_and_transition(self):
        self.assertEqual(self.record["object"], OBJECT)
        self.assertEqual(self.record["record_id"], RECORD_ID)
        self.assertEqual(self.record["from_state"], FROM_STATE)
        self.assertEqual(self.record["to_state"], TO_STATE)

    def test_prior_execution_authorizes_index_mutation(self):
        self.assertEqual(
            self.record["prior_execution_object"],
            "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_EXECUTION_RECORD",
        )
        self.assertTrue(self.record["state_mutation_execution_authorized"])
        self.assertTrue(self.record["current_state_index_mutation_authorized"])
        self.assertTrue(self.record["current_state_index_mutation_executed"])
        self.assertTrue(self.record["current_state_index_now_points_to_to_state"])

    def test_release_candidate_ready_but_not_issued(self):
        self.assertTrue(self.record["release_candidate_ready"])
        self.assertFalse(self.record["issued"])
        self.assertFalse(self.record["media_present"])

    def test_law_authorizes_only_index_mutation(self):
        law = json.loads(self.law_path.read_text())
        self.assertEqual(law["governs_object"], OBJECT)
        self.assertTrue(law["authorizes_current_state_index_mutation_to_release_candidate_ready"])
        self.assertTrue(law["does_not_issue_motion_picture"])
        self.assertTrue(law["does_not_admit_media"])

if __name__ == "__main__":
    unittest.main()
