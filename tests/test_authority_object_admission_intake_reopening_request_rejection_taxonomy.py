import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
REASONS = ['wrong_current_state', 'media_present', 'missing_authority_object_manifest', 'silent_reopening_allowed']

class TestAuthorityObjectAdmissionIntakeReopeningRequestRejectionTaxonomy(unittest.TestCase):
    def test_status_contract(self):
        status = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY_STATUS.json").read_text())
        self.assertEqual(status["current_state"], TARGET)
        self.assertTrue(status["reopening_request_rejection_taxonomy_present"])
        self.assertTrue(status["reopening_request_rejection_taxonomy_sealed"])
        self.assertTrue(status["taxonomy_non_authoritative"])
        self.assertFalse(status["reopening_request_present"])
        self.assertFalse(status["valid_reopening_request_present"])
        self.assertFalse(status["intake_reopening_allowed"])
        self.assertFalse(status["current_snapshot_reopened"])
        self.assertFalse(status["new_snapshot_created"])
        self.assertTrue(status["all_fixtures_rejected"])
        self.assertEqual(status["fixture_count"], 4)

    def test_canonical_reasons(self):
        taxonomy = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY.json").read_text())
        self.assertEqual(taxonomy["current_state"], TARGET)
        self.assertEqual(taxonomy["canonical_rejection_reasons"], REASONS)
        self.assertEqual(taxonomy["canonical_rejection_reason_count"], 4)

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-rejection-taxonomy.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST REJECTION TAXONOMY: PASS", out)
        self.assertIn("CURRENT_STATE=" + TARGET, out)
        self.assertIn("CANONICAL_REJECTION_REASON_COUNT=4", out)

if __name__ == "__main__":
    unittest.main()
