import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
REQUEST_PATTERN = 'fixtures/authority_object_admission_requests/rejected/*.json'
FALSE_KEYS = ['admission_requests_present', 'valid_admission_request_present', 'invalid_admission_requests_present', 'accepted_admission_request_present', 'accepted_authority_request_present', 'release_candidate_ready', 'release_candidate_artifacts_bound', 'issued', 'media_present', 'outsider_replay_passed', 'admissibility_verdict_present', 'terminal_closure_present', 'may_advance_now', 'issuance_unblocked']

class TestAuthorityObjectAdmissionRejectionTaxonomy(unittest.TestCase):
    def test_contract(self):
        data = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json").read_text())
        self.assertEqual(data["current_state"], TARGET)
        self.assertTrue(data['admission_rejection_taxonomy_present'])
        self.assertEqual(data["request_file_pattern"], REQUEST_PATTERN)
        self.assertFalse(data["admission_requests_present"])
        self.assertFalse(data["valid_admission_request_present"])
        self.assertTrue(data["schema_non_authoritative"])
        self.assertTrue(data["validator_non_authoritative"])
        self.assertTrue(data["corpus_non_authoritative"])
        self.assertTrue(data["taxonomy_non_authoritative"])

    def test_non_advancing_surface(self):
        data = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json").read_text())
        for key in FALSE_KEYS:
            self.assertFalse(data[key], key)

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-rejection-taxonomy.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION REJECTION TAXONOMY: PASS", out)
        self.assertIn("REQUEST_FILE_PATTERN=", out)
        self.assertIn("ADMISSION_REQUESTS_PRESENT=false", out)
        self.assertIn("SCHEMAS_DO_NOT_SATISFY_AUTHORITY_OBJECTS=true", out)

if __name__ == "__main__":
    unittest.main()
