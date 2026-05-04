import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class RealCaseAuthorityObjectAdmissionEnforcementGateTest(unittest.TestCase):
    def load(self, rel):
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))

    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-enforcement-gate.sh"],
            cwd=ROOT,
            check=True,
        )

    def test_current_snapshot_is_zero_and_not_enforced_open(self):
        gate = self.load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE.json")
        self.assertEqual(gate["gate_scope"], "REAL_CASE_AUTHORITY_OBJECTS_ONLY")
        self.assertEqual(gate["live_admission_request_count"], 0)
        self.assertEqual(gate["valid_admission_request_count"], 0)
        self.assertEqual(gate["decision_record_count"], 0)
        self.assertEqual(gate["accepted_decision_count"], 0)
        self.assertEqual(gate["rejected_decision_count"], 0)
        self.assertEqual(gate["accepted_authority_object_count"], 0)
        self.assertEqual(gate["instantiated_authority_object_count"], 0)
        self.assertTrue(gate["all_live_admission_requests_have_decisions"])
        self.assertFalse(gate["enforcement_gate_passed"])

    def test_gate_has_no_issuance_power(self):
        gate = self.load("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE.json")
        for key in [
            "gate_does_not_create_live_requests",
            "gate_does_not_validate_requests",
            "gate_does_not_create_decision_records",
            "gate_does_not_accept_requests",
            "gate_does_not_reject_live_requests",
            "gate_does_not_instantiate_authority_objects",
            "gate_does_not_satisfy_authority",
            "gate_does_not_advance_state",
            "gate_does_not_issue_motion_picture",
            "gate_does_not_admit_media",
            "gate_does_not_create_release_candidate",
            "gate_does_not_reopen_current_snapshot",
            "gate_does_not_create_new_snapshot",
        ]:
            self.assertTrue(gate[key], key)
        for key in [
            "authority_satisfied",
            "may_advance_now",
            "release_candidate_ready",
            "issued",
            "media_present",
        ]:
            self.assertFalse(gate[key], key)

if __name__ == "__main__":
    unittest.main()
