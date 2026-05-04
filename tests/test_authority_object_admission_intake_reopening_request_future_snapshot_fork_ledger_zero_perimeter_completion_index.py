import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATUS = ROOT / "CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_ZERO_PERIMETER_COMPLETION_INDEX_STATUS.json"
OBJECT = ROOT / "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_ZERO_PERIMETER_COMPLETION_INDEX.json"
LAW = ROOT / "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_ZERO_PERIMETER_COMPLETION_INDEX_LAW.json"

class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerZeroPerimeterCompletionIndex(unittest.TestCase):
    def setUp(self):
        self.status = json.loads(STATUS.read_text(encoding="utf-8"))
        self.object = json.loads(OBJECT.read_text(encoding="utf-8"))
        self.law = json.loads(LAW.read_text(encoding="utf-8"))

    def test_zero_perimeter_completion_index_present(self):
        self.assertTrue(self.status["ZERO_PERIMETER_COMPLETION_INDEX_PRESENT"])
        self.assertTrue(self.status["ZERO_PERIMETER_COMPLETION_INDEX_SEALED"])
        self.assertTrue(self.status["CURRENT_ZERO_LEDGER_NEGATIVE_PERIMETER_COMPLETE"])
        self.assertFalse(self.status["CURRENT_ZERO_LEDGER_FURTHER_NON_CAPABILITY_SEALS_REQUIRED"])

    def test_all_required_negative_perimeter_seals_are_present(self):
        required = [
            "FUTURE_SNAPSHOT_FORK_LEDGER_TERMINAL_CLOSURE_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_AUTHORITY_SATISFACTION_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_ADVANCEMENT_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_RELEASE_CANDIDATE_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_MEDIA_ADMISSION_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_AUDIENCE_ARTIFACT_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_PROOF_ARTIFACT_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_OUTSIDER_REPLAY_PASSAGE_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_TERMINAL_CLOSURE_INDEX_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_PUBLIC_REPLAY_INDEX_SEALED",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_PUBLIC_INSPECTION_VERDICT_SEALED",
        ]
        for key in required:
            self.assertTrue(self.status[key], key)

    def test_routes_future_work_to_real_intake(self):
        self.assertTrue(self.status["FUTURE_WORK_MUST_ROUTE_TO_REAL_CASE_AUTHORITY_INTAKE"])
        self.assertEqual(self.status["NEXT_REQUIRED_PHASE"], "REAL_CASE_AUTHORITY_INTAKE")
        self.assertEqual(self.status["NEXT_REQUIRED_OBJECT"], "OPEN_REAL_CASE_AUTHORITY_INTAKE")
        self.assertTrue(self.status["ADDITIONAL_NEGATIVE_SEAL_DEFAULT_FORBIDDEN"])
        self.assertEqual(self.law["next_required_route"]["next_object"], "OPEN_REAL_CASE_AUTHORITY_INTAKE")

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

    def test_does_not_open_or_mutate_snapshot(self):
        self.assertFalse(self.status["FUTURE_SNAPSHOT_FORK_GATE_PASSED_NOW"])
        self.assertFalse(self.status["FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW"])
        self.assertEqual(self.status["FUTURE_SNAPSHOT_FORK_RECORD_COUNT"], 0)
        self.assertEqual(self.status["NEW_SNAPSHOT_RECORD_COUNT"], 0)
        self.assertTrue(self.status["ZERO_PERIMETER_COMPLETION_INDEX_DOES_NOT_CREATE_NEW_SNAPSHOT"])
        self.assertTrue(self.status["ZERO_PERIMETER_COMPLETION_INDEX_DOES_NOT_MUTATE_CURRENT_SNAPSHOT"])

if __name__ == "__main__":
    unittest.main()
