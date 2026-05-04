import subprocess
import unittest
from pathlib import Path


class RealCaseAuthorityObjectAdmissionRequestRejectionCorpusTest(unittest.TestCase):
    def test_verifier_passes_and_reports_closed_non_capability_surface(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-request-rejection-corpus.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        out = result.stdout

        self.assertIn(
            "CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REQUEST REJECTION CORPUS: PASS",
            out,
        )
        self.assertIn("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED", out)
        self.assertIn("CORPUS_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY", out)
        self.assertIn("FIXTURES_ARE_LIVE_REQUESTS=false", out)
        self.assertIn("ALL_FIXTURES_REJECTED=true", out)
        self.assertIn("CORPUS_DOES_NOT_CREATE_LIVE_REQUESTS=true", out)
        self.assertIn("CORPUS_DOES_NOT_ACCEPT_REQUESTS=true", out)
        self.assertIn("CORPUS_DOES_NOT_REJECT_LIVE_REQUESTS=true", out)
        self.assertIn("CORPUS_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true", out)
        self.assertIn("CORPUS_DOES_NOT_SATISFY_AUTHORITY=true", out)
        self.assertIn("CORPUS_DOES_NOT_ADVANCE_STATE=true", out)
        self.assertIn("CORPUS_DOES_NOT_ISSUE_MOTION_PICTURE=true", out)
        self.assertIn("CORPUS_DOES_NOT_ADMIT_MEDIA=true", out)
        self.assertIn("CORPUS_DOES_NOT_CREATE_RELEASE_CANDIDATE=true", out)
        self.assertIn("CORPUS_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true", out)
        self.assertIn("CORPUS_DOES_NOT_CREATE_NEW_SNAPSHOT=true", out)
        self.assertIn("AUTHORITY_SATISFIED=false", out)
        self.assertIn("MAY_ADVANCE_NOW=false", out)
        self.assertIn("RELEASE_CANDIDATE_READY=false", out)
        self.assertIn("ISSUED=false", out)
        self.assertIn("MEDIA_PRESENT=false", out)

    def test_required_public_objects_exist(self):
        required = [
            "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json",
            "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_LAW.json",
            "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.md",
            "CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_STATUS.json",
            ".github/workflows/real-case-authority-object-admission-request-rejection-corpus.yml",
        ]
        for path in required:
            self.assertTrue(Path(path).exists(), path)


if __name__ == "__main__":
    unittest.main()
