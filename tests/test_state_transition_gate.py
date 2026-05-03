import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestStateTransitionGate(unittest.TestCase):
    def test_gate_matches_current_state(self):
        gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(gate["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], gate["current_state"])
        self.assertEqual(case["current_state"], gate["current_state"])

    def test_gate_blocks_advancement(self):
        gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
        self.assertEqual(gate["gate_status"], "BLOCKED_FOR_ADVANCEMENT")
        self.assertFalse(gate["may_advance_now"])
        self.assertFalse(gate["next_candidate_state_unblocked"])
        self.assertFalse(gate["final_issuance_state_unblocked"])

    def test_transition_candidates_are_blocked(self):
        gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
        for transition in gate["transition_candidates"]:
            self.assertEqual(transition["status"], "blocked")
            self.assertTrue(transition["missing_required_authority_objects"])

    def test_false_values_remain_false(self):
        gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
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
            self.assertFalse(gate["current_false_values"][key], key)

    def test_status_record_is_not_current_truth(self):
        status = load("CASES/CASE_001_THE_LAST_RENDER/STATE_TRANSITION_GATE_STATUS.json")
        self.assertEqual(status["surface_type"], "LAYER_STATUS_RECORD")
        self.assertFalse(status["current_truth_owner"])
        self.assertFalse(status["may_advance_now"])
        self.assertFalse(status["release_candidate_ready_unblocked"])
        self.assertFalse(status["issuance_unblocked"])

    def test_transition_gate_doc_is_bounded(self):
        text = (ROOT / "STATE_TRANSITION_GATE.md").read_text(encoding="utf-8")
        self.assertIn("may_advance_now=false", text)
        self.assertIn("RELEASE_CANDIDATE_READY", text)
        self.assertIn("ISSUED_ADMISSIBLE_MOTION_PICTURE", text)
        self.assertIn("does not issue a film", text)
        self.assertIn("does not admit media", text)

if __name__ == "__main__":
    unittest.main()
