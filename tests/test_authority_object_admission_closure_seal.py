import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class AuthorityObjectAdmissionClosureSealTest(unittest.TestCase):
    def test_status_is_non_advancing(self):
        status = load_json(
            f"CASES/{CASE_ID}/AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_STATUS.json"
        )
        self.assertEqual(status["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertTrue(status["closure_seal_declared"])
        self.assertTrue(status["admission_stack_closed"])
        self.assertEqual(status["admission_stack_layer_count"], 7)
        self.assertEqual(status["admission_request_count"], 0)
        self.assertEqual(status["decision_record_count"], 0)
        self.assertFalse(status["enforcement_gate_passed"])
        self.assertFalse(status["authority_satisfied"])
        self.assertFalse(status["may_advance_now"])
        self.assertFalse(status["release_candidate_ready"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])

    def test_closure_seal_does_not_satisfy_authority(self):
        seal = load_json("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json")
        self.assertTrue(seal["closure_seal_declared"])
        self.assertTrue(seal["admission_stack_closed"])
        self.assertTrue(seal["seal_does_not_admit_authority_objects"])
        self.assertTrue(seal["seal_does_not_satisfy_authority"])
        self.assertTrue(seal["seal_does_not_advance_state"])
        self.assertFalse(seal["authority_satisfied"])
        self.assertFalse(seal["may_advance_now"])
        self.assertFalse(seal["issued"])
        self.assertFalse(seal["media_present"])

    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-closure-seal.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION CLOSURE SEAL: PASS", result.stdout)
        self.assertIn("ADMISSION_STACK_CLOSED=true", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)


if __name__ == "__main__":
    unittest.main()
