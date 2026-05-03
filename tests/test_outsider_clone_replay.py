import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestOutsiderCloneReplay(unittest.TestCase):
    def test_current_state_is_preserved(self):
        replay = load("OUTSIDER_CLONE_REPLAY.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(replay["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], replay["current_state"])
        self.assertEqual(case["current_state"], replay["current_state"])

    def test_no_private_runtime_dependency(self):
        replay = load("OUTSIDER_CLONE_REPLAY.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_CLONE_REPLAY_STATUS.json")
        self.assertFalse(replay["private_access_required"])
        self.assertFalse(replay["network_required_after_clone"])
        self.assertFalse(replay["media_required"])
        self.assertFalse(replay["model_required"])
        self.assertFalse(replay["paid_api_required"])
        self.assertFalse(replay["cloud_render_required"])
        self.assertFalse(status["private_access_required"])
        self.assertFalse(status["network_required_after_clone"])

    def test_false_claims_remain_false(self):
        replay = load("OUTSIDER_CLONE_REPLAY.json")
        for key in [
            "release_candidate_ready",
            "issued",
            "media_present",
            "generation_present",
            "engine_present",
            "model_present",
            "outsider_replay_passed",
            "valid_transition_attempt_present",
            "may_advance_now",
            "admissibility_verdict_present",
            "terminal_closure_present",
        ]:
            self.assertFalse(replay["expected_false_claims"][key], key)

    def test_manifest_membership(self):
        manifest = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json")
        self.assertIn("scripts/verify-outsider-clone-replay.sh", manifest["required_scripts"])
        self.assertIn("tests/test_outsider_clone_replay.py", manifest["required_unittests"])
        self.assertIn("outsider-clone-replay", manifest["required_ci_workflows"])
        self.assertIn("outsider_clone_replay_requires_no_private_access", manifest["master_invariants"])

    def test_public_document_boundary(self):
        text = (ROOT / "OUTSIDER_CLONE_REPLAY.md").read_text(encoding="utf-8")
        self.assertIn("git clone https://github.com/kaaffilm/CINEMATICUM.git", text)
        self.assertIn("bash scripts/verify-all.sh", text)
        self.assertIn("release_candidate_ready=false", text)
        self.assertIn("issued=false", text)
        self.assertIn("does not issue a film", text)
        self.assertIn("does not create terminal closure", text)

if __name__ == "__main__":
    unittest.main()
