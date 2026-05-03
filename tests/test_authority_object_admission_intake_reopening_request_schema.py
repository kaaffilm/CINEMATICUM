import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"


def load(path):
    with (ROOT / path).open(encoding="utf-8") as f:
        return json.load(f)


class AuthorityObjectAdmissionIntakeReopeningRequestSchemaTest(unittest.TestCase):
    def test_schema_is_not_live_reopening(self):
        schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA_STATUS.json")
        law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA_LAW.json")

        self.assertEqual(
            schema["object_type"],
            "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA",
        )
        self.assertEqual(schema["current_state"], CURRENT_STATE)

        for obj in (schema, status):
            self.assertTrue(obj["schema_only"])
            self.assertTrue(obj["template_only"])
            self.assertEqual(obj["live_reopening_request_count"], 0)
            self.assertEqual(obj["valid_reopening_request_count"], 0)
            self.assertEqual(obj["accepted_reopening_request_count"], 0)
            self.assertTrue(obj["schema_does_not_reopen_intake"])
            self.assertTrue(obj["schema_does_not_create_live_request"])
            self.assertTrue(obj["schema_does_not_satisfy_authority"])
            self.assertTrue(obj["future_request_requires_new_record"])
            self.assertTrue(obj["future_request_requires_schema_validation"])
            self.assertTrue(obj["future_request_requires_decision_record"])
            self.assertTrue(obj["future_request_requires_recomputed_rejection_ledger"])
            self.assertTrue(obj["future_request_requires_new_finality_seal"])
            self.assertTrue(obj["silent_reopening_forbidden"])
            self.assertFalse(obj["reopening_gate_open_now"])
            self.assertTrue(obj["current_snapshot_final"])
            self.assertTrue(obj["intake_finality_sealed"])
            self.assertFalse(obj["authority_satisfied"])
            self.assertFalse(obj["may_advance_now"])
            self.assertFalse(obj["issued"])
            self.assertFalse(obj["media_present"])

        self.assertTrue(law["schema_does_not_reopen_intake"])
        self.assertTrue(law["schema_does_not_create_live_request"])
        self.assertTrue(law["schema_does_not_satisfy_authority"])
        self.assertTrue(law["schema_does_not_advance_case_state"])
        self.assertTrue(law["schema_does_not_issue"])
        self.assertTrue(law["schema_does_not_admit_media"])

    def test_required_reopening_request_fields_are_explicit(self):
        schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA.json")
        required = set(schema["required_reopening_request_fields"])
        expected = {
            "request_id",
            "case_id",
            "target_current_state",
            "requested_authority_object_ids",
            "director_authority_evidence_ref",
            "final_cut_jurisdiction_evidence_ref",
            "timeline_evidence_ref",
            "release_admissibility_evidence_ref",
            "audience_artifact_evidence_ref",
            "proof_artifact_evidence_ref",
            "outsider_replay_evidence_ref",
            "terminal_closure_evidence_ref",
            "reopening_reason",
            "requested_at_utc",
        }
        self.assertTrue(expected.issubset(required))

    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-schema.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST SCHEMA: PASS",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
