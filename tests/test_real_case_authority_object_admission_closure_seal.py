import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestRealCaseAuthorityObjectAdmissionClosureSeal(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-closure-seal.sh"],
            cwd=ROOT,
            check=True,
        )

    def test_closure_is_non_advancing(self):
        seal = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json")
        self.assertTrue(seal["admission_stack_closed"])
        self.assertTrue(seal["closure_seal_declared"])
        self.assertFalse(seal["enforcement_gate_passed"])
        self.assertFalse(seal["authority_satisfied"])
        self.assertFalse(seal["may_advance_now"])
        self.assertFalse(seal["release_candidate_ready"])
        self.assertFalse(seal["issued"])
        self.assertFalse(seal["media_present"])

    def test_zero_request_snapshot_remains_empty(self):
        status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_STATUS.json")
        self.assertEqual(status["live_admission_request_count"], 0)
        self.assertEqual(status["valid_admission_request_count"], 0)
        self.assertEqual(status["decision_record_count"], 0)
        self.assertEqual(status["accepted_decision_count"], 0)
        self.assertEqual(status["rejected_decision_count"], 0)
        self.assertEqual(status["accepted_authority_object_count"], 0)
        self.assertEqual(status["instantiated_authority_object_count"], 0)
        self.assertTrue(status["all_live_admission_requests_have_decisions"])

if __name__ == "__main__":
    unittest.main()
