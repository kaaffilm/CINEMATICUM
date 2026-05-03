import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"


def load(path):
    with (ROOT / path).open(encoding="utf-8") as f:
        return json.load(f)


class AuthorityObjectAdmissionIntakeReopeningGateTest(unittest.TestCase):
    def test_reopening_gate_allows_future_intake_but_not_silent_reopening(self):
        gate = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE_STATUS.json")
        law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE_LAW.json")

        self.assertEqual(
            gate["object_type"],
            "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE",
        )
        self.assertEqual(gate["current_state"], CURRENT_STATE)

        for obj in (gate, status):
            self.assertEqual(obj["reopening_scope"], "FUTURE_VALID_INTAKE_ONLY")
            self.assertTrue(obj["current_snapshot_final"])
            self.assertTrue(obj["future_intake_allowed_under_law"])
            self.assertTrue(obj["future_intake_requires_new_request_record"])
            self.assertTrue(obj["future_intake_requires_schema_validation"])
            self.assertTrue(obj["future_intake_requires_decision_record"])
            self.assertTrue(obj["future_intake_requires_recomputed_rejection_ledger"])
            self.assertTrue(obj["future_intake_requires_new_finality_seal"])
            self.assertTrue(obj["silent_reopening_forbidden"])
            self.assertFalse(obj["reopening_gate_open_now"])
            self.assertEqual(obj["admission_request_count"], 0)
            self.assertEqual(obj["valid_admission_request_count"], 0)
            self.assertEqual(obj["accepted_decision_count"], 0)
            self.assertTrue(obj["intake_finality_sealed"])
            self.assertFalse(obj["authority_satisfied"])
            self.assertFalse(obj["may_advance_now"])
            self.assertFalse(obj["issued"])
            self.assertFalse(obj["media_present"])

        self.assertTrue(law["current_snapshot_final_remains_binding"])
        self.assertTrue(law["future_intake_allowed_under_law"])
        self.assertTrue(law["silent_reopening_forbidden"])
        self.assertTrue(law["does_not_satisfy_authority"])
        self.assertTrue(law["does_not_advance_case_state"])
        self.assertTrue(law["does_not_issue"])
        self.assertTrue(law["does_not_admit_media"])

    def test_finality_seal_explicitly_does_not_bar_future_valid_intake(self):
        finality = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL.json")
        self.assertTrue(finality["intake_finality_sealed"])
        self.assertTrue(finality["does_not_bar_future_valid_intake_under_law"])
        self.assertEqual(finality["finality_scope"], "CURRENT_STATE_ZERO_INTAKE_ONLY")

    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-gate.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING GATE: PASS",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
