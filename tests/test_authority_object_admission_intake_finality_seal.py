import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"


def load(path):
    with (ROOT / path).open(encoding="utf-8") as f:
        return json.load(f)


class AuthorityObjectAdmissionIntakeFinalitySealTest(unittest.TestCase):
    def test_finality_seal_is_current_state_scoped_zero_intake_only(self):
        seal = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL_STATUS.json")
        law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL_LAW.json")

        self.assertEqual(
            seal["object_type"],
            "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL",
        )
        self.assertEqual(
            law["object_type"],
            "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL_LAW",
        )

        for obj in (seal, status):
            self.assertEqual(obj["current_state"], CURRENT_STATE)
            self.assertEqual(obj["finality_scope"], "CURRENT_STATE_ZERO_INTAKE_ONLY")
            self.assertTrue(obj["finality_scope_current_state_only"])
            self.assertTrue(obj["does_not_bar_future_valid_intake_under_law"])
            self.assertTrue(obj["admission_stack_closed"])
            self.assertEqual(obj["required_authority_object_count"], 8)
            self.assertEqual(obj["admission_request_count"], 0)
            self.assertEqual(obj["valid_admission_request_count"], 0)
            self.assertEqual(obj["accepted_decision_count"], 0)
            self.assertFalse(obj["intake_validation_gate_passed"])
            self.assertEqual(obj["intake_rejection_record_count"], 0)
            self.assertTrue(obj["rejection_ledger_closed"])
            self.assertTrue(obj["all_invalid_intake_rejected"])
            self.assertTrue(obj["no_open_intake_exceptions"])
            self.assertTrue(obj["no_unadjudicated_intake_records"])
            self.assertTrue(obj["intake_finality_sealed"])
            self.assertFalse(obj["authority_satisfied"])
            self.assertFalse(obj["may_advance_now"])
            self.assertFalse(obj["issued"])
            self.assertFalse(obj["media_present"])

        self.assertTrue(law["seals_current_zero_intake_snapshot"])
        self.assertTrue(law["finality_scope_current_state_only"])
        self.assertTrue(law["does_not_bar_future_valid_intake_under_law"])
        self.assertTrue(law["does_not_satisfy_authority"])
        self.assertTrue(law["does_not_advance_case_state"])
        self.assertTrue(law["does_not_issue"])
        self.assertTrue(law["does_not_admit_media"])

    def test_rejection_ledger_is_required_and_closed(self):
        ledger = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REJECTION_LEDGER.json")
        self.assertTrue(ledger["rejection_ledger_closed"])
        self.assertTrue(ledger["all_invalid_intake_rejected"])
        self.assertEqual(ledger["intake_rejection_record_count"], 0)
        self.assertFalse(ledger["authority_satisfied"])
        self.assertFalse(ledger["may_advance_now"])

    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-finality-seal.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE FINALITY SEAL: PASS",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
