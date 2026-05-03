import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CinematicIssuanceDocketTest(unittest.TestCase):
    def load(self, path):
        return json.loads((ROOT / path).read_text())

    def test_issuance_docket_identity(self):
        docket = self.load("ISSUANCE_DOCKET.json")
        self.assertEqual(docket["institution"], "CINEMATICUM")
        self.assertEqual(docket["issued_object"], "admissible_motion_picture")
        self.assertTrue(docket["issuance_is_not_export"])
        self.assertTrue(docket["issuance_is_not_generation"])
        self.assertIn("terminal_closure", docket["issuance_requires"])

    def test_film_object_has_three_bodies(self):
        anatomy = self.load("ADMISSIBLE_FILM_OBJECT_ANATOMY.json")
        self.assertIn("audience_body", anatomy["three_bodies"])
        self.assertIn("evidentiary_body", anatomy["three_bodies"])
        self.assertIn("jurisdictional_body", anatomy["three_bodies"])
        self.assertTrue(anatomy["film_is_inadmissible_if_any_body_missing"])

    def test_departments_are_authorities(self):
        ledger = self.load("DEPARTMENT_AUTHORITY_LEDGER.json")
        self.assertEqual(ledger["department_status"], "decision_authorities_not_scripts")
        self.assertEqual(ledger["model_output_status"], "raw_material_only")
        departments = {d["department"] for d in ledger["departments"]}
        self.assertGreaterEqual(
            departments,
            {"director", "cinematographer", "editor", "sound", "release_archivist"},
        )

    def test_case_001_docket(self):
        case = self.load("CASES/CASE_001_THE_LAST_RENDER/CASE_DOCKET.json")
        self.assertEqual(case["docket_number"], "CIN-0001")
        self.assertEqual(case["title"], "THE LAST RENDER")
        self.assertTrue(case["not_demo"])
        self.assertTrue(case["not_model_showcase"])
        self.assertTrue(case["not_prompt_pipeline"])

    def test_case_evidence_not_yet_media_or_engine(self):
        evidence = self.load("CASES/CASE_001_THE_LAST_RENDER/CASE_EVIDENCE_LEDGER.json")
        self.assertFalse(evidence["media_admitted"])
        self.assertFalse(evidence["generation_admitted"])
        self.assertFalse(evidence["engine_admitted"])

    def test_verify_script(self):
        with tempfile.TemporaryDirectory() as d:
            receipt = Path(d) / "receipt.json"
            env = os.environ.copy()
            env["RECEIPT_PATH"] = str(receipt)
            subprocess.run(
                ["bash", "scripts/verify-cinematic-issuance-docket.sh"],
                cwd=ROOT,
                env=env,
                check=True,
            )
            data = json.loads(receipt.read_text())
            self.assertTrue(data["pass"])
            self.assertEqual(data["docket_number"], "CIN-0001")
            self.assertFalse(data["media_admitted"])
            self.assertFalse(data["generation_admitted"])
            self.assertFalse(data["engine_admitted"])

if __name__ == "__main__":
    unittest.main()
