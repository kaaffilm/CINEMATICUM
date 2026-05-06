import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestPublicPerimeterSentinel(unittest.TestCase):
    def test_sentinel_matches_current_state(self):
        sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(sentinel["current_state"], "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], sentinel["current_state"])
        self.assertEqual(case["current_state"], sentinel["current_state"])

    def test_public_inspection_chain_exists(self):
        sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
        for path in sentinel["public_inspection_chain"] + sentinel["machine_truth_chain"]:
            self.assertTrue((ROOT / path).exists(), path)

    def test_required_verifiers_exist(self):
        sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
        for path in sentinel["required_verifiers"]:
            self.assertTrue((ROOT / path).exists(), path)

    def test_perimeter_status_blocks_private_payload_and_transition(self):
        sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
        perimeter = sentinel["perimeter_status"]
        self.assertFalse(perimeter["private_access_required"])
        self.assertFalse(perimeter["media_or_model_payload_present"])
        self.assertFalse(perimeter["forbidden_private_file_present"])
        self.assertFalse(perimeter["valid_transition_attempt_present"])
        self.assertFalse(perimeter["may_advance_now"])
        self.assertTrue(perimeter["required_authority_objects_missing"])

    def test_forbidden_transition_attempt_object_types_absent(self):
        sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
        forbidden = set(sentinel["forbidden_transition_attempt_object_types"])

        present = set()
        for path in ROOT.rglob("*.json"):
            if ".git" in path.parts:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            object_type = data.get("object_type")
            if object_type:
                present.add(object_type)

        self.assertTrue(forbidden.isdisjoint(present), forbidden & present)

    def test_false_values_remain_false(self):
        sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
        for key in [
            "release_candidate_ready",
            "issued",
            "media_present",
            "generation_present",
            "engine_present",
            "model_present",
            "outsider_replay_passed",
            "admissibility_verdict_present",
            "terminal_closure_present",
        ]:
            self.assertFalse(sentinel["current_false_values"][key], key)

    def test_public_perimeter_doc_is_bounded(self):
        text = (ROOT / "PUBLIC_PERIMETER_SENTINEL.md").read_text(encoding="utf-8")
        self.assertIn("private_access_required=false", text)
        self.assertIn("media_or_model_payload_present=false", text)
        self.assertIn("valid_transition_attempt_present=false", text)
        self.assertIn("raw media", text)
        self.assertIn("model weights", text)
        self.assertIn("does not issue a film", text)
        self.assertIn("does not admit media", text)

if __name__ == "__main__":
    unittest.main()
