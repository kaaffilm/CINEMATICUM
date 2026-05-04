import json
import subprocess
import unittest
from pathlib import Path


class TestRealCaseAuthorityObjectSlotIndex(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-slot-index.sh"],
            check=True,
        )

    def test_contract_has_eight_unfilled_slots(self):
        data = json.loads(Path("CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX.json").read_text())
        slots = data["authority_object_slots"]

        self.assertEqual(data["object_type"], "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_SLOT_INDEX")
        self.assertEqual(data["authority_object_slot_count"], 8)
        self.assertEqual(len(slots), 8)
        self.assertEqual([slot["slot_number"] for slot in slots], list(range(1, 9)))
        self.assertEqual({slot["slot_status"] for slot in slots}, {"UNFILLED"})
        self.assertEqual(data["accepted_authority_object_count"], 0)
        self.assertEqual(data["instantiated_authority_object_count"], 0)
        self.assertFalse(data["authority_satisfied"])
        self.assertFalse(data["may_advance_now"])
        self.assertFalse(data["release_candidate_ready"])
        self.assertFalse(data["issued"])
        self.assertFalse(data["media_present"])
