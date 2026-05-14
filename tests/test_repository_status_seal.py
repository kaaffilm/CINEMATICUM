import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestRepositoryStatusSeal(unittest.TestCase):
    def test_repository_status_is_substance_gated(self):
        seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
        self.assertEqual(seal["current_state"], "RELEASE_CANDIDATE_READY")
        self.assertFalse(seal["issued"])
        self.assertIsNone(seal.get("issued_object"))
        self.assertFalse(seal["media_present"])
        self.assertFalse(seal["media_substance_passed"])
        self.assertEqual(seal["blocked_by"], "MEDIA_SUBSTANCE_GATE")

    def test_no_motion_picture_media_issuance_without_substance(self):
        seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
        for key in (
            "motion_picture_media_issuance_ready",
            "admissible_motion_picture_issued",
            "motion_picture_issued",
            "motion_picture_media_issued",
            "final_master_media_issued",
        ):
            self.assertFalse(seal.get(key, False), key)
        self.assertFalse(seal["raw_media_stored_in_git"])

    def test_public_status_doc_is_bounded(self):
        text = (ROOT / "PUBLIC_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("mission_done=false", text)
        self.assertIn("issued=false", text)
        self.assertIn("media_substance_passed=false", text)
        self.assertIn("blocked_by=MEDIA_SUBSTANCE_GATE", text)

if __name__ == "__main__":
    unittest.main()
