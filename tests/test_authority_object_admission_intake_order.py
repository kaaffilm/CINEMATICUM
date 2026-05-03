import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    with (ROOT / path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


class AuthorityObjectAdmissionIntakeOrderTest(unittest.TestCase):
    def test_intake_order_is_closed_but_non_satisfying(self):
        obj = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER.json")
        self.assertEqual(obj["case_id"], "CASE_001_THE_LAST_RENDER")
        self.assertEqual(obj["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertTrue(obj["depends_on_admission_closure_seal"])
        self.assertTrue(obj["intake_order_is_not_authority_satisfaction"])
        self.assertFalse(obj["authority_satisfied"])
        self.assertFalse(obj["may_advance_now"])
        self.assertFalse(obj["issued"])
        self.assertFalse(obj["media_present"])

    def test_required_authority_object_order_is_complete(self):
        obj = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER.json")
        required = obj["required_authority_objects"]
        self.assertEqual(len(required), 8)
        self.assertEqual(obj["required_authority_object_count"], 8)
        self.assertEqual([item["order"] for item in required], list(range(1, 9)))
        self.assertEqual(
            [item["authority_object_type"] for item in required],
            [
                "DIRECTOR_ACCEPTANCE_OBJECT",
                "FINAL_CUT_TIMELINE_LOCK",
                "MEDIA_HASH_MANIFEST",
                "COLOR_GRADE_LOCK",
                "SOUND_MIX_LOCK",
                "REPLAY_EXECUTION_REPORT",
                "ADMISSIBILITY_VERDICT",
                "TERMINAL_CLOSURE_CANDIDATE",
            ],
        )
        for item in required:
            self.assertTrue((ROOT / item["template_path"]).exists(), item["template_path"])
            self.assertTrue((ROOT / item["schema_path"]).exists(), item["schema_path"])

    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-order.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE ORDER: PASS", result.stdout)
        self.assertIn("REQUIRED_AUTHORITY_OBJECT_COUNT=8", result.stdout)


if __name__ == "__main__":
    unittest.main()
