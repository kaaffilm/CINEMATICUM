import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATUS = ROOT / "CASES/CASE_001_THE_LAST_RENDER/NON_STAR_SEAL_REDUNDANCY_STOP_RULE_STATUS.json"
OBJECT = ROOT / "CINEMATICUM_NON_STAR_SEAL_REDUNDANCY_STOP_RULE.json"
LAW = ROOT / "CINEMATICUM_NON_STAR_SEAL_REDUNDANCY_STOP_RULE_LAW.json"

class TestNonStarSealRedundancyStopRule(unittest.TestCase):
    def setUp(self):
        self.status = json.loads(STATUS.read_text(encoding="utf-8"))
        self.object = json.loads(OBJECT.read_text(encoding="utf-8"))
        self.law = json.loads(LAW.read_text(encoding="utf-8"))

    def test_rule_present_and_not_a_new_non_star_seal(self):
        self.assertTrue(self.status["NON_STAR_SEAL_REDUNDANCY_STOP_RULE_PRESENT"])
        self.assertTrue(self.status["NON_STAR_SEAL_REDUNDANCY_STOP_RULE_SEALED"])
        self.assertFalse(self.status["RULE_CREATES_NON_STAR_SEAL_ARTIFACT"])
        self.assertFalse(self.object["creates_non_star_seal"])
        self.assertEqual(self.object["canonical_rule_name"], "NON_*_SEAL_REDUNDANCY_STOP_RULE")

    def test_depends_on_zero_perimeter_completion(self):
        self.assertTrue(self.status["ZERO_PERIMETER_COMPLETION_INDEX_PRESENT"])
        self.assertTrue(self.status["ZERO_PERIMETER_COMPLETION_INDEX_SEALED"])
        self.assertTrue(self.status["CURRENT_ZERO_LEDGER_NEGATIVE_PERIMETER_COMPLETE"])
        self.assertFalse(self.status["CURRENT_ZERO_LEDGER_FURTHER_NON_CAPABILITY_SEALS_REQUIRED"])
        self.assertIn(
            "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_ZERO_PERIMETER_COMPLETION_INDEX",
            self.law["depends_on"],
        )

    def test_redundant_non_star_seals_forbidden(self):
        self.assertTrue(self.status["ADDITIONAL_NON_STAR_SEAL_DEFAULT_FORBIDDEN"])
        self.assertTrue(self.status["ADDITIONAL_NON_STAR_SEAL_ALLOWED_ONLY_IF_REQUIRED_TO_UNBLOCK_REAL_INTAKE"])
        self.assertTrue(self.status["ADDITIONAL_NON_STAR_SEAL_MUST_NAME_UNBLOCKED_REAL_INTAKE_GATE"])
        self.assertTrue(self.status["ADDITIONAL_NON_STAR_SEAL_MUST_NOT_RECLASSIFY_CURRENT_ZERO_LEDGER"])
        self.assertTrue(self.status["ADDITIONAL_NON_STAR_SEAL_MUST_NOT_DELAY_REAL_CASE_AUTHORITY_INTAKE"])

    def test_routes_to_real_case_authority_intake(self):
        self.assertTrue(self.status["FUTURE_WORK_MUST_ROUTE_TO_REAL_CASE_AUTHORITY_INTAKE"])
        self.assertEqual(self.status["NEXT_REQUIRED_PHASE"], "REAL_CASE_AUTHORITY_INTAKE")
        self.assertEqual(self.status["NEXT_REQUIRED_OBJECT"], "CURRENT_ZERO_LEDGER_NO_FURTHER_ADVANCEMENT_PROOF")
        self.assertEqual(self.status["TRANSITION_REQUEST_OBJECT"], "OPEN_REAL_CASE_AUTHORITY_INTAKE")

    def test_does_not_advance_or_issue(self):
        for key in [
            "AUTHORITY_SATISFIED",
            "MAY_ADVANCE_NOW",
            "RELEASE_CANDIDATE_READY",
            "ISSUED",
            "MEDIA_PRESENT",
            "AUDIENCE_ARTIFACT_PRESENT",
            "PROOF_ARTIFACT_PRESENT",
            "OUTSIDER_REPLAY_PASSED",
        ]:
            self.assertFalse(self.status[key], key)

    def test_does_not_mutate_snapshot(self):
        self.assertFalse(self.status["FUTURE_SNAPSHOT_FORK_GATE_PASSED_NOW"])
        self.assertFalse(self.status["FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW"])
        self.assertEqual(self.status["FUTURE_SNAPSHOT_FORK_RECORD_COUNT"], 0)
        self.assertEqual(self.status["NEW_SNAPSHOT_RECORD_COUNT"], 0)
        self.assertTrue(self.status["STOP_RULE_DOES_NOT_CREATE_NEW_SNAPSHOT"])
        self.assertTrue(self.status["STOP_RULE_DOES_NOT_MUTATE_CURRENT_SNAPSHOT"])

if __name__ == "__main__":
    unittest.main()
