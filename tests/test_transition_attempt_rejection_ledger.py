import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestTransitionAttemptRejectionLedger(unittest.TestCase):
    def test_ledger_matches_current_state(self):
        ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(ledger["current_state"], "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], ledger["current_state"])
        self.assertEqual(case["current_state"], ledger["current_state"])

    def test_no_transition_attempts_recorded(self):
        ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
        self.assertEqual(ledger["attempt_counts"]["recorded"], 0)
        self.assertEqual(ledger["attempt_counts"]["accepted"], 0)
        self.assertEqual(ledger["attempt_counts"]["rejected"], 0)
        self.assertEqual(ledger["transition_attempt_records"], [])
        self.assertFalse(ledger["valid_transition_attempt_present"])
        self.assertFalse(ledger["invalid_transition_attempt_present"])

    def test_automatic_rejection_rules_cover_blocked_targets(self):
        ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
        targets = {rule["target_state"] for rule in ledger["automatic_rejection_rules"]}
        self.assertEqual(targets, {"REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", "ISSUED_ADMISSIBLE_MOTION_PICTURE"})
        for rule in ledger["automatic_rejection_rules"]:
            self.assertTrue(rule["would_be_rejected_now"])

    def test_forbidden_attempt_objects_do_not_exist(self):
        ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
        forbidden = set(ledger["forbidden_attempt_object_types"])
        present = set()
        for path in ROOT.rglob("*.json"):
            if ".git" in path.parts:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            object_type = data.get("object_type")
            if object_type:
                present.add(object_type)
        self.assertTrue(forbidden.isdisjoint(present), forbidden & present)

    def test_gate_and_checklist_still_block(self):
        ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
        gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
        checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
        self.assertFalse(ledger["may_advance_now"])
        self.assertFalse(gate["may_advance_now"])
        self.assertTrue(checklist["required_authority_objects_missing"])

    def test_false_values_remain_false(self):
        ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
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
            self.assertFalse(ledger["current_false_values"][key], key)

    def test_rejection_doc_is_bounded(self):
        text = (ROOT / "TRANSITION_ATTEMPT_REJECTION_LEDGER.md").read_text(encoding="utf-8")
        self.assertIn("transition_attempts_recorded=0", text)
        self.assertIn("valid_transition_attempt_present=false", text)
        self.assertIn("CINEMATICUM_STATE_TRANSITION_ATTEMPT", text)
        self.assertIn("does not issue a film", text)
        self.assertIn("does not admit media", text)

if __name__ == "__main__":
    unittest.main()
