import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestRealCaseAuthorityObjectAdmissionFinalitySeal(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-finality-seal.sh"],
            cwd=ROOT,
            check=True,
        )

    def test_current_zero_snapshot_final_and_immutable(self):
        seal = load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL.json")
        self.assertTrue(seal["current_zero_admission_snapshot_final"])
        self.assertFalse(seal["current_zero_admission_snapshot_mutable"])
        self.assertTrue(seal["future_valid_admission_requests_allowed_under_law"])
        self.assertTrue(seal["future_valid_admission_requests_do_not_mutate_current_zero_snapshot"])

    def test_finality_is_non_advancing(self):
        status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL_STATUS.json")
        self.assertFalse(status["enforcement_gate_passed"])
        self.assertFalse(status["authority_satisfied"])
        self.assertFalse(status["may_advance_now"])
        self.assertFalse(status["release_candidate_ready"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])

    def test_zero_admission_snapshot_remains_empty(self):
        status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FINALITY_SEAL_STATUS.json")
        for key in [
            "live_admission_request_count",
            "valid_admission_request_count",
            "invalid_admission_request_count",
            "decision_record_count",
            "accepted_decision_count",
            "rejected_decision_count",
            "accepted_authority_object_count",
            "instantiated_authority_object_count",
        ]:
            self.assertEqual(status[key], 0, key)
        self.assertTrue(status["no_unadjudicated_admission_records"])

if __name__ == "__main__":
    unittest.main()
