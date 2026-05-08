import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestRepositoryStatusSeal(unittest.TestCase):
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

    def test_false_claims_remain_false(self):
        seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
        for key in [
                        "issued",
            "media_present",
            "generation_present",
            "engine_present",
            "model_present",
            "outsider_replay_passed",
            "admissibility_verdict_present",
            "terminal_closure_present",
        ]:
            self.assertFalse(seal[key], key)

    def test_required_verification_flags(self):
        seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
        self.assertTrue(seal["verify_all_pass_required"])
        self.assertTrue(seal["object_registry_fresh_required"])

    def test_public_status_doc_is_bounded(self):
        text = (ROOT / "PUBLIC_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("RELEASE_CANDIDATE_READY", text)
        self.assertIn("release_candidate_ready=true", text)
        self.assertIn("issued=false", text)
        self.assertIn("media_present=false", text)
        self.assertIn("does not issue a film", text)

if __name__ == "__main__":
    unittest.main()
