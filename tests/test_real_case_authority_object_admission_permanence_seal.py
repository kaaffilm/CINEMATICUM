import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestRealCaseAuthorityObjectAdmissionPermanenceSeal(unittest.TestCase):
    def load(self, rel):
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))

    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-permanence-seal.sh"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        self.assertIn("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION PERMANENCE SEAL: PASS", result.stdout)

    def test_permanence_preserves_terminal_zero_snapshot(self):
        doc = self.load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_PERMANENCE_SEAL.json")
        self.assertTrue(doc["current_zero_admission_snapshot_terminal"])
        self.assertTrue(doc["current_zero_admission_snapshot_permanent"])
        self.assertFalse(doc["current_zero_admission_snapshot_mutable"])
        self.assertTrue(doc["current_zero_admission_snapshot_closed_against_reclassification"])
        self.assertTrue(doc["future_valid_admission_requests_must_target_future_snapshot"])
        self.assertTrue(doc["future_valid_admission_requests_create_new_snapshot"])
        self.assertTrue(doc["future_valid_admission_requests_do_not_mutate_current_zero_snapshot"])
        self.assertTrue(doc["future_valid_admission_requests_do_not_mutate_terminal_snapshot"])

    def test_permanence_does_not_satisfy_authority_or_advance(self):
        doc = self.load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_PERMANENCE_SEAL.json")
        self.assertFalse(doc["authority_satisfied"])
        self.assertFalse(doc["may_advance_now"])
        self.assertFalse(doc["release_candidate_ready"])
        self.assertFalse(doc["issued"])
        self.assertFalse(doc["media_present"])
        self.assertFalse(doc["enforcement_gate_passed"])
        self.assertTrue(doc["permanence_seal_does_not_satisfy_authority"])
        self.assertTrue(doc["permanence_seal_does_not_advance_state"])
        self.assertTrue(doc["permanence_seal_does_not_issue_motion_picture"])
        self.assertTrue(doc["permanence_seal_does_not_admit_media"])
        self.assertTrue(doc["permanence_seal_does_not_create_release_candidate"])
        self.assertTrue(doc["permanence_seal_does_not_create_new_snapshot_now"])

    def test_status_matches_permanence_core(self):
        doc = self.load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_PERMANENCE_SEAL.json")
        status = self.load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_PERMANENCE_SEAL_STATUS.json")
        keys = [
            "current_state",
            "permanence_scope",
            "admission_stack_layer_count",
            "admission_stack_closed",
            "current_zero_admission_snapshot_final",
            "current_zero_admission_snapshot_terminal",
            "current_zero_admission_snapshot_permanent",
            "current_zero_admission_snapshot_mutable",
            "future_valid_admission_requests_must_target_future_snapshot",
            "future_valid_admission_requests_do_not_mutate_current_zero_snapshot",
            "authority_satisfied",
            "may_advance_now",
            "issued",
            "media_present"
        ]
        for key in keys:
            self.assertEqual(doc[key], status[key])

    def test_law_is_non_issuing_permanence_only(self):
        law = self.load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_PERMANENCE_SEAL_LAW.json")
        self.assertTrue(law["requires_closure_seal"])
        self.assertTrue(law["requires_finality_seal"])
        self.assertTrue(law["requires_terminal_seal"])
        self.assertTrue(law["declares_current_zero_admission_snapshot_permanent"])
        self.assertFalse(law["declares_current_zero_admission_snapshot_mutable"])
        self.assertTrue(law["forbids_silent_snapshot_mutation"])
        self.assertTrue(law["forbids_terminal_snapshot_mutation"])
        self.assertTrue(law["permanence_does_not_convert_zero_snapshot_into_authority"])
        self.assertFalse(law["authority_satisfied"])
        self.assertFalse(law["may_advance_now"])
        self.assertFalse(law["issued"])
        self.assertFalse(law["media_present"])

if __name__ == "__main__":
    unittest.main()
