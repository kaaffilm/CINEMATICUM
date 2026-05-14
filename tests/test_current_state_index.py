import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"
STATE = "RELEASE_CANDIDATE_READY"


class TestCurrentStateIndex(unittest.TestCase):
    def read_json(self, rel):
        return json.loads((ROOT / rel).read_text())

    def test_root_index_is_active_current_state_owner(self):
        index = self.read_json("CINEMATICUM_CURRENT_STATE_INDEX.json")

        self.assertEqual(index["active_case_states"][CASE_ID], STATE)
        self.assertEqual(index["active_current_state"], STATE)
        self.assertEqual(index.get("issued_films", []), [])

    def test_case_current_state_is_active_and_not_issued(self):
        case = self.read_json("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

        self.assertEqual(case["current_state"], STATE)
        self.assertTrue(case.get("release_candidate_ready"))
        self.assertFalse(case.get("issued"))
        self.assertFalse(case.get("media_present"))
        self.assertFalse(case.get("motion_picture_issued", False))
        self.assertFalse(case.get("admissible_motion_picture_issued", False))
        self.assertFalse(case.get("motion_picture_media_issuance_ready", False))

    def test_index_does_not_claim_motion_picture_media_issuance(self):
        index = self.read_json("CINEMATICUM_CURRENT_STATE_INDEX.json")

        self.assertFalse(index.get("issued", False))
        self.assertFalse(index.get("media_present", False))
        self.assertFalse(index.get("motion_picture_issued", False))
        self.assertFalse(index.get("admissible_motion_picture_issued", False))
        self.assertFalse(index.get("motion_picture_media_issuance_ready", False))

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-current-state-index.sh"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout

        self.assertIn("CINEMATICUM CURRENT STATE INDEX: PASS", out)
        self.assertIn("CURRENT_STATE=RELEASE_CANDIDATE_READY", out)
        self.assertIn("ISSUED=false", out)
        self.assertIn("MEDIA_PRESENT=false", out)


if __name__ == "__main__":
    unittest.main()
