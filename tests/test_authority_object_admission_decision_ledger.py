import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

def load_optional(path: str):
    p = ROOT / path
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

def get(obj, *names, default=None):
    for name in names:
        if name in obj:
            return obj[name]
    return default

def count(obj, *names):
    value = get(obj, *names, default=0)
    assert isinstance(value, int)
    return value

def flag(obj, *names):
    value = get(obj, *names, default=False)
    assert isinstance(value, bool)
    return value

def reason_code(item):
    return item["code"] if isinstance(item, dict) else item

class AuthorityObjectAdmissionDecisionLedgerTest(unittest.TestCase):
    def setUp(self):
        self.ledger = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json")
        self.status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_STATUS.json")
        self.docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
        self.validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
        self.taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
        self.state_index = load_optional("CINEMATICUM_CURRENT_STATE_INDEX.json")

    def active_state(self):
        return (
            get(self.ledger, "current_state", "active_current_state")
            or get(self.status, "current_state", "active_current_state")
            or get(self.state_index, "active_current_state", "current_state")
        )

    def test_current_state_is_not_advanced(self):
        self.assertEqual(self.active_state(), "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertFalse(flag(self.ledger, "authority_satisfied"))
        self.assertFalse(flag(self.ledger, "may_advance_now"))
        self.assertFalse(flag(self.ledger, "release_candidate_ready"))
        self.assertFalse(flag(self.ledger, "issued"))
        self.assertFalse(flag(self.ledger, "media_present"))

    def test_counts_are_zero_state_consistent(self):
        admission_count = count(self.ledger, "admission_request_count", "live_admission_request_count")
        decision_count = count(self.ledger, "decision_record_count", "admission_decision_count")
        accepted_count = count(self.ledger, "accepted_decision_count")
        rejected_count = count(self.ledger, "rejected_decision_count")

        self.assertEqual(admission_count, 0)
        self.assertEqual(decision_count, accepted_count + rejected_count)
        self.assertEqual(count(self.docket, "admission_request_count"), admission_count)
        self.assertEqual(count(self.validator, "admission_request_count"), admission_count)

    def test_presence_aliases_match_counts(self):
        admission_count = count(self.ledger, "admission_request_count", "live_admission_request_count")
        decision_count = count(self.ledger, "decision_record_count", "admission_decision_count")
        accepted_count = count(self.ledger, "accepted_decision_count")
        rejected_count = count(self.ledger, "rejected_decision_count")

        self.assertIs(flag(self.ledger, "admission_requests_present", "live_admission_requests_present"), admission_count > 0)
        self.assertIs(flag(self.ledger, "decision_records_present"), decision_count > 0)
        self.assertIs(flag(self.ledger, "accepted_decisions_present"), accepted_count > 0)
        self.assertIs(flag(self.ledger, "rejected_decisions_present"), rejected_count > 0)

    def test_rejected_decisions_use_canonical_taxonomy(self):
        taxonomy_codes = {reason_code(item) for item in self.taxonomy["canonical_rejection_reasons"]}
        self.assertTrue(all(isinstance(code, str) and code for code in taxonomy_codes))

        for record in self.ledger.get("decision_records", []):
            self.assertIn(record["decision"], {"ACCEPTED", "REJECTED"})
            if record["decision"] == "REJECTED":
                self.assertIn(record["rejection_reason"], taxonomy_codes)

    def test_status_mirrors_ledger(self):
        for key in [
            "admission_request_count",
            "live_admission_request_count",
            "decision_record_count",
            "admission_decision_count",
            "accepted_decision_count",
            "rejected_decision_count",
            "authority_satisfied",
            "may_advance_now",
            "release_candidate_ready",
            "issued",
            "media_present",
        ]:
            self.assertEqual(self.status.get(key), self.ledger.get(key), key)

if __name__ == "__main__":
    unittest.main()
