import subprocess
import unittest


class TestRealCaseAuthorityObjectAdmissionRejectionTaxonomy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-rejection-taxonomy.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        cls.output = result.stdout

    def test_taxonomy_passes(self):
        self.assertIn(
            "CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REJECTION TAXONOMY: PASS",
            self.output,
        )
        self.assertIn("TAXONOMY_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY", self.output)
        self.assertIn("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_PRESENT=true", self.output)
        self.assertIn("REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_SEALED=true", self.output)

    def test_taxonomy_is_fixture_only_and_non_advancing(self):
        required = [
            "FIXTURES_ARE_LIVE_REQUESTS=false",
            "LIVE_ADMISSION_REQUEST_COUNT=0",
            "VALID_ADMISSION_REQUEST_COUNT=0",
            "ACCEPTED_ADMISSION_REQUEST_COUNT=0",
            "ACCEPTED_AUTHORITY_OBJECT_COUNT=0",
            "INSTANTIATED_AUTHORITY_OBJECT_COUNT=0",
            "TAXONOMY_DOES_NOT_CREATE_LIVE_REQUESTS=true",
            "TAXONOMY_DOES_NOT_ACCEPT_REQUESTS=true",
            "TAXONOMY_DOES_NOT_REJECT_LIVE_REQUESTS=true",
            "TAXONOMY_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true",
            "TAXONOMY_DOES_NOT_SATISFY_AUTHORITY=true",
            "TAXONOMY_DOES_NOT_ADVANCE_STATE=true",
            "TAXONOMY_DOES_NOT_ISSUE_MOTION_PICTURE=true",
            "TAXONOMY_DOES_NOT_ADMIT_MEDIA=true",
            "TAXONOMY_DOES_NOT_CREATE_RELEASE_CANDIDATE=true",
            "TAXONOMY_DOES_NOT_REOPEN_CURRENT_SNAPSHOT=true",
            "TAXONOMY_DOES_NOT_CREATE_NEW_SNAPSHOT=true",
            "AUTHORITY_SATISFIED=false",
            "MAY_ADVANCE_NOW=false",
            "RELEASE_CANDIDATE_READY=false",
            "ISSUED=false",
            "MEDIA_PRESENT=false",
        ]
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, self.output)

    def test_taxonomy_counts_are_reported(self):
        for token in [
            "CANONICAL_REJECTION_REASON_COUNT=",
            "COVERED_REJECTION_REASON_COUNT=",
            "UNCOVERED_REJECTION_REASON_COUNT=",
            "TAXONOMY_COMPLETE_FOR_CURRENT_VALIDATOR=true",
            "CORPUS_COMPLETE_FOR_REQUIRED_REASONS=true",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.output)


if __name__ == "__main__":
    unittest.main()
