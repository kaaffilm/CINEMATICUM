import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str):
    with (ROOT / path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


class AuthorityObjectAdmissionEnforcementGateTest(unittest.TestCase):
    def test_gate_status_blocks_advance(self):
        status = load_json("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_STATUS.json")
        self.assertEqual(status["object_type"], "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_STATUS")
        self.assertEqual(status["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertEqual(status["admission_request_count"], 0)
        self.assertEqual(status["decision_record_count"], 0)
        self.assertEqual(status["accepted_decision_count"], 0)
        self.assertEqual(status["rejected_decision_count"], 0)
        self.assertTrue(status["all_live_requests_have_decisions"])
        self.assertTrue(status["accepted_decision_for_each_instantiated_authority_object"])
        self.assertFalse(status["enforcement_gate_passed"])
        self.assertFalse(status["authority_satisfied"])
        self.assertFalse(status["may_advance_now"])
        self.assertFalse(status["release_candidate_ready"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])

    def test_gate_law_does_not_issue_or_admit_media(self):
        law = load_json("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_LAW.json")
        self.assertEqual(law["object_type"], "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_LAW")
        self.assertTrue(law["live_authority_object_requires_admission_decision"])
        self.assertTrue(law["accepted_admission_decision_required_before_instantiation"])
        self.assertTrue(law["missing_decision_blocks_instantiation"])
        self.assertTrue(law["rejected_decision_blocks_instantiation"])
        self.assertTrue(law["enforcement_gate_does_not_admit_media"])
        self.assertTrue(law["enforcement_gate_does_not_create_release_candidate"])
        self.assertTrue(law["enforcement_gate_does_not_issue_motion_picture"])

    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-enforcement-gate.sh"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION ENFORCEMENT GATE: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
