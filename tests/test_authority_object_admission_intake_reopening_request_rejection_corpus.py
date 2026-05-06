import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
FIXTURES = {
    "wrong-current-state.json": "wrong_current_state",
    "media-present.json": "media_present",
    "missing-authority-object-manifest.json": "missing_authority_object_manifest",
    "silent-reopening-allowed.json": "silent_reopening_allowed",
}

class TestAuthorityObjectAdmissionIntakeReopeningRequestRejectionCorpus(unittest.TestCase):
    def test_status_contract(self):
        status = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS_STATUS.json").read_text())
        self.assertEqual(status["current_state"], TARGET)
        self.assertTrue(status["reopening_request_rejection_corpus_present"])
        self.assertTrue(status["reopening_request_rejection_corpus_sealed"])
        self.assertTrue(status["corpus_non_authoritative"])
        self.assertFalse(status["reopening_request_present"])
        self.assertFalse(status["valid_reopening_request_present"])
        self.assertFalse(status["intake_reopening_allowed"])
        self.assertFalse(status["current_snapshot_reopened"])
        self.assertFalse(status["new_snapshot_created"])
        self.assertTrue(status["all_fixtures_rejected"])
        self.assertEqual(status["fixture_count"], 4)

    def test_fixtures_rejected(self):
        root = Path("fixtures/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS")
        for filename, reason in FIXTURES.items():
            fixture = json.loads((root / filename).read_text())
            self.assertEqual(fixture["current_state"], TARGET)
            self.assertEqual(fixture["expected_rejection_reason"], reason)
            self.assertEqual(fixture["rejection_reason"], reason)
            self.assertFalse(fixture["live_request"])
            self.assertFalse(fixture["accepted"])
            self.assertFalse(fixture["valid"])
            self.assertTrue(fixture["rejected"])

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-rejection-corpus.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST REJECTION CORPUS: PASS", out)
        self.assertIn("CURRENT_STATE=" + TARGET, out)
        self.assertIn("ALL_FIXTURES_REJECTED=true", out)

if __name__ == "__main__":
    unittest.main()
