import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"
STATE = "RELEASE_CANDIDATE_READY"


class TestRepositoryStatusSeal(unittest.TestCase):
    def load_json(self, rel):
        return json.loads((ROOT / rel).read_text())

    def test_seal_matches_current_state_owners(self):
        index = self.load_json("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = self.load_json("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        seal = self.load_json("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")

        self.assertEqual(index["active_case_states"][CASE_ID], STATE)
        self.assertEqual(index["active_current_state"], STATE)
        self.assertEqual(case["current_state"], STATE)
        self.assertEqual(seal["active_current_state"], STATE)
        self.assertEqual(seal["current_state"], STATE)

    def test_release_candidate_repository_status_claims_do_not_issue_media(self):
        seal = self.load_json("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")

        self.assertTrue(seal["protocol_issued"])
        self.assertTrue(seal["protocol_perimeter_issued"])
        self.assertTrue(seal["protocol_film_issued"])
        self.assertTrue(seal["release_candidate_ready"])

        for key in [
            "issued",
            "media_present",
            "media_payload_present",
            "motion_picture_media_issuance_ready",
            "admissible_motion_picture_issued",
            "motion_picture_issued",
            "raw_media_stored_in_git",
            "private_access_required",
            "admissibility_verdict_present",
            "terminal_closure_present",
            "outsider_replay_passed",
            "generation_present",
            "engine_present",
            "model_present",
            "model_weight_payload_present",
        ]:
            self.assertFalse(seal[key], key)

        self.assertIsNone(seal["issued_object"])

    def test_no_media_admission_metadata_is_claimed(self):
        seal = self.load_json("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")

        for key in [
            "media_sha256",
            "media_bytes",
            "media_mime",
            "media_uri",
            "media_name",
            "motion_picture_media_admission_record",
            "motion_picture_issuance_act",
        ]:
            self.assertNotIn(key, seal)

    def test_forbidden_readings_include_media_boundary(self):
        seal = self.load_json("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
        forbidden = "\n".join(seal["forbidden_readings"])

        self.assertIn("protocol film issuance means final-master media issuance", forbidden)
        self.assertIn("admits media without a hash-bound media admission record", forbidden)
        self.assertIn("raw media is stored in git", forbidden)

    def test_public_status_doc_is_bounded(self):
        text = (ROOT / "PUBLIC_STATUS.md").read_text()

        self.assertIn("RELEASE_CANDIDATE_READY", text)
        self.assertIn("protocol_issued=true", text)
        self.assertIn("unqualified_issued=false", text)
        self.assertIn("motion_picture_media_issued=false", text)
        self.assertIn("motion_picture_issued=false", text)
        self.assertIn("admissible_motion_picture_issued=false", text)
        self.assertIn("motion_picture_media_issuance_ready=false", text)
        self.assertIn("media_present=false", text)
        self.assertIn("does not issue motion-picture media", text)
        self.assertIn("remains false at release-candidate readiness", text)

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-repository-status-seal.sh"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout

        self.assertIn("CINEMATICUM REPOSITORY STATUS SEAL: PASS", out)
        self.assertIn("CURRENT_STATE=RELEASE_CANDIDATE_READY", out)
        self.assertIn("ISSUED=false", out)
        self.assertIn("MEDIA_PRESENT=false", out)
        self.assertIn("MOTION_PICTURE_MEDIA_ISSUANCE_READY=false", out)


if __name__ == "__main__":
    unittest.main()
