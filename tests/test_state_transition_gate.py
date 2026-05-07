import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'RELEASE_CANDIDATE_READY'
NEXT = 'RELEASE_CANDIDATE_ARTIFACTS_BOUND'
CASE = 'CASE_001_THE_LAST_RENDER'

class TestStateTransitionGate(unittest.TestCase):
    def test_gate_blocks_advancement(self):
        gate = json.loads(Path("CINEMATICUM_STATE_TRANSITION_GATE.json").read_text())
        self.assertEqual(gate["current_state"], TARGET)
        self.assertEqual(gate["next_required_state"], NEXT)
        self.assertEqual(gate["next_required_object"], "RELEASE_CANDIDATE_GAP_LEDGER")
        self.assertTrue(gate["authority_object_stack_complete"])
        self.assertEqual(gate["accepted_authority_object_count"], 8)
        self.assertEqual(gate["instantiated_authority_object_count"], 8)
        self.assertEqual(gate["unfilled_authority_object_slot_count"], 0)
        self.assertTrue(gate["release_candidate_ready"])
        self.assertFalse(gate["release_candidate_artifacts_bound"])
        self.assertFalse(gate["issued"])
        self.assertFalse(gate["media_present"])
        self.assertFalse(gate["outsider_replay_passed"])
        self.assertFalse(gate["admissibility_verdict_present"])
        self.assertFalse(gate["terminal_closure_present"])
        self.assertFalse(gate["may_advance_now"])
        self.assertFalse(gate["issuance_unblocked"])

    def test_transition_candidate_is_blocked(self):
        gate = json.loads(Path("CINEMATICUM_STATE_TRANSITION_GATE.json").read_text())
        candidate = gate["transition_candidates"][0]
        self.assertEqual(candidate["from_state"], TARGET)
        self.assertEqual(candidate["to_state"], NEXT)
        self.assertFalse(candidate["may_advance_now"])
        self.assertTrue(candidate["blocked"])

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-state-transition-gate.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM STATE TRANSITION GATE: PASS", out)
        self.assertIn(f"CURRENT_STATE={TARGET}", out)
        self.assertIn("MAY_ADVANCE_NOW=false", out)

if __name__ == "__main__":
    unittest.main()
