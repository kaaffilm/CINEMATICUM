import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"


def load(path):
    with (ROOT / path).open(encoding="utf-8") as f:
        return json.load(f)


class AuthorityObjectAdmissionIntakeReopeningRequestValidatorTest(unittest.TestCase):
    def test_validator_preserves_zero_live_reopening(self):
        validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR_STATUS.json")
        law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR_LAW.json")

        self.assertEqual(
            validator["object_type"],
            "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR",
        )
        self.assertEqual(validator["current_state"], CURRENT_STATE)

        for obj in (validator, status):
            self.assertEqual(obj["live_reopening_request_count"], 0)
            self.assertEqual(obj["valid_reopening_request_count"], 0)
            self.assertEqual(obj["invalid_reopening_request_count"], 0)
            self.assertEqual(obj["accepted_reopening_request_count"], 0)
            self.assertTrue(obj["zero_reopening_requests_valid"])
            self.assertTrue(obj["validator_declared"])
            self.assertTrue(obj["validator_does_not_create_live_request"])
            self.assertTrue(obj["validator_does_not_reopen_intake"])
            self.assertTrue(obj["validator_does_not_satisfy_authority"])
            self.assertTrue(obj["validator_does_not_advance_case_state"])
            self.assertTrue(obj["future_request_must_match_schema"])
            self.assertTrue(obj["future_request_must_have_decision_before_reopening"])
            self.assertTrue(obj["future_request_must_recompute_finality"])
            self.assertTrue(obj["silent_reopening_forbidden"])
            self.assertFalse(obj["reopening_gate_open_now"])
            self.assertTrue(obj["current_snapshot_final"])
            self.assertTrue(obj["intake_finality_sealed"])
            self.assertFalse(obj["authority_satisfied"])
            self.assertFalse(obj["may_advance_now"])
            self.assertFalse(obj["issued"])
            self.assertFalse(obj["media_present"])

        self.assertTrue(law["validator_does_not_create_live_request"])
        self.assertTrue(law["validator_does_not_reopen_intake"])
        self.assertTrue(law["validator_does_not_satisfy_authority"])
        self.assertTrue(law["validator_does_not_advance_case_state"])
        self.assertTrue(law["validator_does_not_issue"])
        self.assertTrue(law["validator_does_not_admit_media"])

    def test_request_directory_has_no_live_requests(self):
        validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR.json")
        request_dir = ROOT / validator["live_reopening_request_directory"]
        if request_dir.exists():
            self.assertEqual(sorted(request_dir.glob("*.json")), [])

    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-validator.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST VALIDATOR: PASS",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
