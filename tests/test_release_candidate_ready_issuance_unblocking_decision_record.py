import json, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBJ = "RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_DECISION_RECORD"

class TestReleaseCandidateReadyIssuanceUnblockingDecisionRecord(unittest.TestCase):
    def setUp(self):
        self.r = json.loads((ROOT / f"{OBJ}.json").read_text())
        self.c = json.loads((ROOT / "CASES/CASE_001_THE_LAST_RENDER" / f"{OBJ}_STATUS.json").read_text())

    def test_decision_identity(self):
        self.assertEqual(self.r["DECISION_OBJECT"], OBJ)
        self.assertEqual(self.r["DECISION_ID"], "DEC_001_RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING")
        self.assertEqual(self.r["REQUEST_OBJECT"], "RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_REQUEST")
        self.assertEqual(self.r["REQUEST_ID"], "REQ_001_RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_REQUEST")
        self.assertEqual(self.r["REQUIRED_PRIOR_OBJECT"], "RELEASE_CANDIDATE_READY_ISSUANCE_BLOCKADE_SEAL")
        self.assertEqual(self.r["NEXT_REQUIRED_OBJECT"], "RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_EXECUTION_RECORD")

    def test_decision_authorizes_but_does_not_execute(self):
        self.assertTrue(self.r["DECISION_ACCEPTS_REQUEST"])
        self.assertTrue(self.r["DECISION_AUTHORIZES_ISSUANCE_UNBLOCKING"])
        self.assertTrue(self.r["ISSUANCE_UNBLOCKING_EXECUTION_RECORD_REQUIRED_BEFORE_UNBLOCKING"])
        self.assertTrue(self.r["DECISION_DOES_NOT_UNBLOCK_ISSUANCE"])

    def test_no_issuance_side_effects(self):
        for rec in (self.r, self.c):
            self.assertFalse(rec["MAY_ADVANCE_NOW"])
            self.assertFalse(rec["ISSUANCE_UNBLOCKED"])
            self.assertFalse(rec["ISSUED"])
            self.assertFalse(rec["MEDIA_PRESENT"])
            self.assertTrue(rec["CURRENT_STATE_UNCHANGED"])

if __name__ == "__main__":
    unittest.main()
