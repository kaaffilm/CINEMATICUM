import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"


def load(path):
    with (ROOT / path).open(encoding="utf-8") as f:
        return json.load(f)


class AuthorityObjectAdmissionIntakeRejectionLedgerTest(unittest.TestCase):
    def test_rejection_ledger_is_closed_zero_record_negative_layer(self):
        ledger = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REJECTION_LEDGER.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REJECTION_LEDGER_STATUS.json")
        law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REJECTION_LEDGER_LAW.json")

        self.assertEqual(
            ledger["object_type"],
            "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REJECTION_LEDGER",
        )
        self.assertEqual(
            law["object_type"],
            "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REJECTION_LEDGER_LAW",
        )

        for obj in (ledger, status):
            self.assertEqual(obj["current_state"], CURRENT_STATE)
            self.assertTrue(obj["admission_stack_closed"])
            self.assertEqual(obj["required_authority_object_count"], 8)
            self.assertEqual(obj["admission_request_count"], 0)
            self.assertEqual(obj["valid_admission_request_count"], 0)
            self.assertEqual(obj["accepted_decision_count"], 0)
            self.assertFalse(obj["intake_validation_gate_passed"])
            self.assertEqual(obj["intake_rejection_record_count"], 0)
            self.assertFalse(obj["live_intake_rejections_required"])
            self.assertTrue(obj["all_invalid_intake_rejected"])
            self.assertTrue(obj["rejection_ledger_closed"])
            self.assertFalse(obj["authority_satisfied"])
            self.assertFalse(obj["may_advance_now"])
            self.assertFalse(obj["issued"])
            self.assertFalse(obj["media_present"])

        self.assertTrue(law["records_negative_intake_adjudication"])
        self.assertTrue(law["zero_valid_intake_requires_zero_rejection_records"])
        self.assertTrue(law["does_not_create_admission_requests"])
        self.assertTrue(law["does_not_accept_authority_objects"])
        self.assertTrue(law["does_not_instantiate_authority_objects"])
        self.assertTrue(law["does_not_satisfy_authority"])
        self.assertTrue(law["does_not_advance_case_state"])
        self.assertTrue(law["does_not_issue"])
        self.assertTrue(law["does_not_admit_media"])

    def test_prior_validation_gate_remains_blocking(self):
        validation = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE.json")
        self.assertFalse(validation["intake_validation_gate_passed"])
        self.assertEqual(validation["valid_admission_request_count"], 0)
        self.assertFalse(validation["authority_satisfied"])
        self.assertFalse(validation["may_advance_now"])
        self.assertFalse(validation["issued"])
        self.assertFalse(validation["media_present"])

    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-rejection-ledger.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REJECTION LEDGER: PASS",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
