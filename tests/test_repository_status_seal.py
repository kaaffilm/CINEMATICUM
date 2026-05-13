from pathlib import Path
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class TestRepositoryStatusSeal(unittest.TestCase):
    def load_seal(self):
        return json.loads(Path("CINEMATICUM_REPOSITORY_STATUS_SEAL.json").read_text())

    def test_seal_matches_current_state_owners(self):
        seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

        self.assertEqual(seal["current_state"], "RELEASE_CANDIDATE_READY")
        self.assertTrue(seal["release_candidate_ready"])
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], seal["current_state"])
        self.assertEqual(case["current_state"], seal["current_state"])

    def test_seal_is_not_current_truth_owner(self):
        seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")

        self.assertFalse(seal["seal_is_current_truth_owner"])
        self.assertEqual(seal["current_truth_owner"], "CINEMATICUM_CURRENT_STATE_INDEX.json")
        self.assertEqual(seal["case_current_truth_owner"], "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

    def test_no_media_boundary_is_not_bare_issuance(self):
        seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")

        self.assertEqual(seal["active_current_state"], "RELEASE_CANDIDATE_READY")
        self.assertEqual(seal.get("issuance_type"), "PROTOCOL_FILM")

        self.assertTrue(seal["issued"])
        self.assertTrue(seal["media_present"])
        self.assertTrue(seal["motion_picture_media_issuance_ready"])
        self.assertTrue(seal.get("admissible_motion_picture_issued", False))
        self.assertTrue(seal.get("motion_picture_issued", False))

    def test_hash_bound_motion_picture_media_claims_are_true_without_raw_git_payload(self):
        seal = self.load_seal()
        for key in [
            "issued",
            "media_present",
            "motion_picture_media_issuance_ready",
            "admissible_motion_picture_issued",
            "motion_picture_issued",
        ]:
            self.assertTrue(seal[key], key)

        self.assertTrue(seal["protocol_film_issued"])
        self.assertTrue(seal["protocol_perimeter_issued"])
        self.assertFalse(seal["raw_media_stored_in_git"])
        self.assertFalse(seal["media_payload_present"])
        self.assertFalse(seal["outsider_replay_passed"])
        self.assertTrue(seal["private_access_required"])
        self.assertEqual(
            seal["motion_picture_media_admission_record"],
            "records/motion_picture_issuance/MOTION_PICTURE_MEDIA_ADMISSION_RECORD.json",
        )

    def test_required_verification_flags(self):
        seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")

        self.assertTrue(seal["verify_all_pass_required"])
        self.assertTrue(seal["object_registry_fresh_required"])

    def test_public_status_doc_is_bounded(self):
        text = (ROOT / "PUBLIC_STATUS.md").read_text(encoding="utf-8")

        self.assertIn("RELEASE_CANDIDATE_READY", text)
        self.assertIn("release_candidate_ready=true", text)
        self.assertIn("issued=true", text)
        self.assertIn("issuance_type=PROTOCOL_FILM", text)
        self.assertIn("media_present=true", text)
        self.assertIn("does not by itself issue motion-picture media", text)
        self.assertIsNone(re.search(r"(?m)^\s+issued=false\s*$", text))


if __name__ == "__main__":
    unittest.main()
