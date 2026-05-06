import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
AUTHORITY_OBJECTS = ['CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/EDITORIAL_TIMELINE_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/SOUND_FINAL_MIX_LOCK_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/COLOR_GRADE_LOCK_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/RELEASE_DELIVERY_ARTIFACTS_LOCK_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/ARCHIVIST_PROOF_CHAIN_LOCK_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/OUTSIDER_REPLAY_PASSAGE_AUTHORITY_OBJECT.json', 'CASES/CASE_001_THE_LAST_RENDER/FUTURE_REAL_CASE_AUTHORITY_OBJECTS/TERMINAL_CLOSURE_AUTHORITY_OBJECT.json']
FALSE_KEYS = ['release_candidate_ready', 'release_candidate_artifacts_bound', 'issued', 'media_present', 'outsider_replay_passed', 'admissibility_verdict_present', 'terminal_closure_present', 'may_advance_now', 'issuance_unblocked']

class TestAuthorityObjectInstantiationGate(unittest.TestCase):
    def test_instantiation_gate_contract(self):
        data = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json").read_text())
        self.assertEqual(data["current_state"], TARGET)
        self.assertTrue(data["authority_object_instantiation_gate_passed"])
        self.assertTrue(data["authority_object_stack_complete"])
        self.assertFalse(data["required_authority_objects_missing"])
        self.assertEqual(data["accepted_authority_object_count"], 8)
        self.assertEqual(data["instantiated_authority_object_count"], 8)
        self.assertEqual(data["unfilled_authority_object_slot_count"], 0)
        self.assertEqual(data["instantiated_authority_object_paths"], AUTHORITY_OBJECTS)

    def test_instantiated_objects_exist_and_do_not_issue(self):
        for rel in AUTHORITY_OBJECTS:
            p = Path(rel)
            self.assertTrue(p.exists(), rel)
            data = json.loads(p.read_text())
            self.assertEqual(data["current_state"], TARGET)
            self.assertTrue(data.get("instantiated"), rel)
            self.assertTrue(data.get("accepted"), rel)
            for key in FALSE_KEYS:
                self.assertFalse(data.get(key), f"{rel}:{key}")

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-instantiation-gate.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT INSTANTIATION GATE: PASS", out)
        self.assertIn("AUTHORITY_OBJECT_STACK_COMPLETE=true", out)
        self.assertIn("INSTANTIATED_AUTHORITY_OBJECT_COUNT=8", out)

if __name__ == "__main__":
    unittest.main()
