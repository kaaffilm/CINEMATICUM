import json, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBJ = "RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_REQUEST"

class TestReleaseCandidateReadyIssuanceUnblockingRequest(unittest.TestCase):
    def setUp(self):
        self.r = json.loads((ROOT / f"{OBJ}.json").read_text())
        self.c = json.loads((ROOT / "CASES/CASE_001_THE_LAST_RENDER" / f"{OBJ}_STATUS.json").read_text())

    def test_request_identity(self):
        self.assertEqual(self.r["REQUEST_OBJECT"], OBJ)
        self.assertEqual(self.r["REQUEST_ID"], "REQ_001_RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_REQUEST")
        self.assertEqual(self.r["REQUIRED_PRIOR_OBJECT"], "RELEASE_CANDIDATE_READY_ISSUANCE_BLOCKADE_SEAL")
        self.assertEqual(self.r["NEXT_REQUIRED_OBJECT"], "RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_DECISION_RECORD")

    def test_request_only(self):
        self.assertTrue(self.r["REQUEST_IS_NOT_DECISION"])
        self.assertTrue(self.r["REQUEST_DOES_NOT_UNBLOCK_ISSUANCE"])
        self.assertTrue(self.r["DECISION_RECORD_REQUIRED_BEFORE_ISSUANCE_UNBLOCKING"])

    def test_no_side_effects(self):
        for rec in (self.r, self.c):
            self.assertFalse(rec["MAY_ADVANCE_NOW"])
            self.assertFalse(rec["ISSUANCE_UNBLOCKED"])
            self.assertFalse(rec["ISSUED"])
            self.assertFalse(rec["MEDIA_PRESENT"])
            self.assertTrue(rec["CURRENT_STATE_UNCHANGED"])

if __name__ == "__main__":
    unittest.main()
