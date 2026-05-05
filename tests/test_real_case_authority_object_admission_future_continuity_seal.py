import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "CASES" / "CASE_001_THE_LAST_RENDER"

def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

class TestRealCaseAuthorityObjectAdmissionFutureContinuitySeal(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-future-continuity-seal.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION FUTURE CONTINUITY SEAL: PASS",
            result.stdout,
        )

    def test_future_requests_route_to_future_snapshot(self):
        obj = load(ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL.json")
        future = obj["future_admission_request_law"]
        self.assertTrue(future["future_valid_admission_requests_must_target_future_snapshot"])
        self.assertTrue(future["future_valid_admission_requests_create_new_snapshot"])
        self.assertTrue(future["future_valid_admission_requests_do_not_mutate_current_zero_snapshot"])
        self.assertTrue(future["future_valid_admission_requests_do_not_mutate_terminal_snapshot"])

    def test_current_zero_snapshot_remains_permanent(self):
        obj = load(ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL.json")
        self.assertTrue(obj["current_zero_snapshot"]["permanent"])
        self.assertFalse(obj["current_zero_snapshot"]["mutable"])
        self.assertTrue(obj["current_zero_snapshot"]["terminal"])
        self.assertTrue(obj["current_zero_snapshot"]["closed_against_reclassification"])

    def test_no_authority_or_issuance_side_effects(self):
        obj = load(ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL.json")
        status = obj["status"]
        self.assertFalse(status["authority_satisfied"])
        self.assertFalse(status["may_advance_now"])
        self.assertFalse(status["release_candidate_ready"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])
        self.assertTrue(obj["non_effects"]["does_not_accept_authority_object_now"])
        self.assertTrue(obj["non_effects"]["does_not_instantiate_authority_object_now"])

    def test_first_future_slot_candidate_declared_without_filling(self):
        obj = load(ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_FUTURE_CONTINUITY_SEAL.json")
        route = obj["authority_slot_route"]
        self.assertEqual(route["authority_object_slot_count"], 8)
        self.assertEqual(route["first_future_authority_slot_candidate"], "DIRECTOR_ACCEPTANCE_OBJECT")
        self.assertEqual(route["accepted_authority_object_count_now"], 0)
        self.assertEqual(route["instantiated_authority_object_count_now"], 0)
        self.assertTrue(route["slot_filling_allowed_only_in_future_snapshot"])

if __name__ == "__main__":
    unittest.main()
