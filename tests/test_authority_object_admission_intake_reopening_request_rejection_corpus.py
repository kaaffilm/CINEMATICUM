import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"


def load(path):
    with (ROOT / path).open(encoding="utf-8") as f:
        return json.load(f)


class AuthorityObjectAdmissionIntakeReopeningRequestRejectionCorpusTest(unittest.TestCase):
    def test_rejection_corpus_is_fixture_only(self):
        corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS_STATUS.json")
        law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS_LAW.json")

        self.assertEqual(
            corpus["object_type"],
            "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS",
        )
        self.assertEqual(corpus["current_state"], CURRENT_STATE)

        for obj in (corpus, status):
            self.assertEqual(obj["canonical_rejection_fixture_count"], 5)
            self.assertFalse(obj["fixtures_are_live_requests"])
            self.assertTrue(obj["all_fixtures_rejected"])
            self.assertEqual(obj["live_reopening_request_count"], 0)
            self.assertEqual(obj["valid_reopening_request_count"], 0)
            self.assertEqual(obj["accepted_reopening_request_count"], 0)
            self.assertTrue(obj["rejection_corpus_declared"])
            self.assertTrue(obj["rejection_corpus_does_not_create_live_request"])
            self.assertTrue(obj["rejection_corpus_does_not_reopen_intake"])
            self.assertTrue(obj["rejection_corpus_does_not_satisfy_authority"])
            self.assertTrue(obj["rejection_corpus_does_not_advance_case_state"])
            self.assertTrue(obj["silent_reopening_forbidden"])
            self.assertFalse(obj["authority_satisfied"])
            self.assertFalse(obj["may_advance_now"])
            self.assertFalse(obj["issued"])
            self.assertFalse(obj["media_present"])

        self.assertFalse(law["fixtures_are_live_requests"])
        self.assertTrue(law["all_fixtures_must_be_rejected"])
        self.assertTrue(law["fixtures_must_not_reopen_intake"])
        self.assertTrue(law["fixtures_must_not_satisfy_authority"])
        self.assertTrue(law["fixtures_must_not_advance_case_state"])
        self.assertTrue(law["live_reopening_request_count_must_remain_zero"])

    def test_fixtures_are_not_live_requests(self):
        corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS.json")
        fixture_dir = ROOT / corpus["fixture_directory"]
        fixture_files = sorted(fixture_dir.glob("*.json"))
        self.assertEqual(len(fixture_files), 5)

        reasons = set()
        for fixture_file in fixture_files:
            fixture = json.loads(fixture_file.read_text(encoding="utf-8"))
            self.assertEqual(fixture["fixture_type"], "CINEMATICUM_REOPENING_REQUEST_REJECTION_FIXTURE")
            self.assertFalse(fixture["fixture_is_live_request"])
            self.assertFalse(fixture["expected_valid"])
            reasons.add(fixture["expected_rejection_reason"])

        self.assertEqual(
            reasons,
            {
                "missing_current_state",
                "wrong_current_state",
                "missing_authority_object_manifest",
                "silent_reopening_allowed",
                "media_present",
            },
        )

    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-rejection-corpus.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST REJECTION CORPUS: PASS",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
