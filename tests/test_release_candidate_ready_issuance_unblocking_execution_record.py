import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"

class ReleaseCandidateReadyIssuanceUnblockingExecutionRecordTest(unittest.TestCase):
    def setUp(self):
        self.record = json.loads((ROOT / "RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_EXECUTION_RECORD.json").read_text())
        self.status = json.loads((ROOT / "CASES" / CASE_ID / "RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_EXECUTION_RECORD_STATUS.json").read_text())

    def test_execution_record_present_and_identity(self):
        self.assertEqual(self.record["object_type"], "RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_EXECUTION_RECORD")
        self.assertEqual(self.record["execution_id"], "EXEC_001_RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING")
        self.assertEqual(self.record["case_id"], CASE_ID)

    def test_execution_unblocks_but_does_not_issue(self):
        self.assertTrue(self.record["issuance_unblocking_execution_authorized"])
        self.assertTrue(self.record["issuance_unblocking_executed"])
        self.assertTrue(self.record["issuance_unblocked"])
        self.assertFalse(self.record["issued"])
        self.assertFalse(self.record["media_present"])
        self.assertTrue(self.record["execution_record_does_not_issue_motion_picture"])
        self.assertTrue(self.record["execution_record_does_not_admit_media"])

    def test_status_matches_execution_boundary(self):
        self.assertTrue(self.status["release_candidate_ready"])
        self.assertTrue(self.status["issuance_unblocking_execution_record_present"])
        self.assertTrue(self.status["issuance_unblocked"])
        self.assertFalse(self.status["issued"])
        self.assertFalse(self.status["media_present"])
        self.assertEqual(self.status["next_required_object"], "MOTION_PICTURE_ISSUANCE_ACT")

if __name__ == "__main__":
    unittest.main()
