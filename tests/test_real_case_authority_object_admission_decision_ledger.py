import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestRealCaseAuthorityObjectAdmissionDecisionLedger(unittest.TestCase):
    def test_verifier_passes_and_reports_boundary(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-decision-ledger.sh"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        output = result.stdout
        self.assertIn("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION DECISION LEDGER: PASS", output)
        self.assertIn("LEDGER_SCOPE=REAL_CASE_AUTHORITY_OBJECTS_ONLY", output)
        self.assertIn("DECISION_RECORD_COUNT=0", output)
        self.assertIn("ALL_LIVE_ADMISSION_REQUESTS_HAVE_DECISIONS=true", output)
        self.assertIn("AUTHORITY_SATISFIED=false", output)
        self.assertIn("MAY_ADVANCE_NOW=false", output)
        self.assertIn("ISSUED=false", output)
        self.assertIn("MEDIA_PRESENT=false", output)

    def test_ledger_is_zero_decision_non_advancing_surface(self):
        ledger = json.loads(
            (ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(ledger["object_id"], "REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER")
        self.assertEqual(ledger["ledger_scope"], "REAL_CASE_AUTHORITY_OBJECTS_ONLY")
        self.assertEqual(ledger["decision_records"], [])
        self.assertEqual(ledger["decision_record_count"], 0)
        self.assertEqual(ledger["accepted_decision_count"], 0)
        self.assertEqual(ledger["rejected_decision_count"], 0)
        self.assertEqual(ledger["accepted_authority_object_count"], 0)
        self.assertEqual(ledger["instantiated_authority_object_count"], 0)
        self.assertTrue(ledger["all_live_admission_requests_have_decisions"])
        self.assertFalse(ledger["authority_satisfied"])
        self.assertFalse(ledger["may_advance_now"])
        self.assertFalse(ledger["release_candidate_ready"])
        self.assertFalse(ledger["issued"])
        self.assertFalse(ledger["media_present"])

    def test_law_preserves_future_decision_only_scope(self):
        law = json.loads(
            (ROOT / "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_LAW.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(law["decision_records_required_for_future_valid_requests"])
        self.assertTrue(law["zero_current_live_requests_yields_zero_decisions"])
        self.assertTrue(law["accepted_decisions_do_not_instantiate_authority_objects_without_later_enforcement"])
        self.assertTrue(law["rejected_decisions_do_not_apply_to_fixture_only_corpus_requests"])
        self.assertTrue(law["ledger_does_not_satisfy_authority"])
        self.assertTrue(law["ledger_does_not_advance_state"])


if __name__ == "__main__":
    unittest.main()
