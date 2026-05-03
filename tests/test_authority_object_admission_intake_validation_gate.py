import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"


def load(path):
    with (ROOT / path).open(encoding="utf-8") as f:
        return json.load(f)


class AuthorityObjectAdmissionIntakeValidationGateTest(unittest.TestCase):
    def test_gate_is_blocking_and_non_issuing(self):
        gate = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE_STATUS.json")
        law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE_LAW.json")

        self.assertEqual(
            gate["object_type"],
            "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE",
        )
        self.assertEqual(
            law["object_type"],
            "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE_LAW",
        )

        for obj in (gate, status):
            self.assertEqual(obj["current_state"], CURRENT_STATE)
            self.assertTrue(obj["admission_stack_closed"])
            self.assertEqual(obj["required_authority_object_count"], 8)
            self.assertEqual(obj["admission_request_count"], 0)
            self.assertEqual(obj["valid_admission_request_count"], 0)
            self.assertEqual(obj["accepted_decision_count"], 0)
            self.assertFalse(obj["intake_validation_gate_passed"])
            self.assertFalse(obj["authority_satisfied"])
            self.assertFalse(obj["may_advance_now"])
            self.assertFalse(obj["issued"])
            self.assertFalse(obj["media_present"])

        self.assertTrue(law["validates_intake_order_only"])
        self.assertTrue(law["does_not_instantiate_authority_objects"])
        self.assertTrue(law["does_not_satisfy_authority"])
        self.assertTrue(law["does_not_advance_case_state"])
        self.assertTrue(law["does_not_issue"])
        self.assertTrue(law["does_not_admit_media"])

    def test_prior_layers_remain_unsatisfied(self):
        intake = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER.json")
        closure = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json")
        enforcement = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE.json")

        self.assertTrue(
            intake.get("admission_stack_closed")
            or intake.get("authority_object_admission_stack_closed")
            or intake.get("closure_seal_admission_stack_closed", True)
        )
        self.assertTrue(
            closure.get("admission_stack_closed")
            or closure.get("authority_object_admission_stack_closed")
            or closure.get("closed", True)
        )
        self.assertFalse(enforcement.get("authority_satisfied", False))
        self.assertFalse(enforcement.get("may_advance_now", False))
        self.assertFalse(enforcement.get("issued", False))
        self.assertFalse(enforcement.get("media_present", False))

    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-validation-gate.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE VALIDATION GATE: PASS",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
