import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CinematicJurisdictionTest(unittest.TestCase):
    def load(self, path):
        return json.loads((ROOT / path).read_text())

    def test_charter_identity(self):
        charter = self.load("CHARTER_OF_CINEMATIC_JURISDICTION.json")
        self.assertEqual(charter["root_sentence"], "CINEMATICUM issues admissible motion pictures.")
        self.assertEqual(charter["institution"], "CINEMATICUM")
        self.assertEqual(charter["repo"], "kaaffilm/CINEMATICUM")
        self.assertEqual(charter["primary_form"], "sovereign_cinematic_jurisdiction")
        self.assertEqual(charter["issued_object"], "admissible_motion_picture")
        self.assertEqual(charter["first_case"], "CASE_001_THE_LAST_RENDER")
        self.assertEqual(charter["first_case_title"], "THE LAST RENDER")
        self.assertTrue(charter["local_only"])
        self.assertFalse(charter["paid_api_allowed"])
        self.assertFalse(charter["cloud_render_allowed"])
        self.assertFalse(charter["raw_media_in_git"])
        self.assertFalse(charter["model_weights_in_git"])

    def test_admissible_motion_picture_standard(self):
        standard = self.load("ADMISSIBLE_MOTION_PICTURE_STANDARD.json")
        self.assertEqual(standard["object_type"], "admissible_motion_picture")
        self.assertIn("final_audience_experience", standard["audience_body_required"])
        self.assertIn("outsider_replay_proof", standard["evidentiary_body_required"])
        self.assertIn("terminal_closure", standard["evidentiary_body_required"])

    def test_forbidden_reductions(self):
        forbidden = set(self.load("FORBIDDEN_REDUCTIONS.json")["forbidden_reductions"])
        for item in {
            "ai_video_generator",
            "prompt_pipeline",
            "model_showcase",
            "demo_clip",
            "automation_wrapper",
            "render_farm",
            "workflow_collection",
        }:
            self.assertIn(item, forbidden)

    def test_case_001_not_demo(self):
        case = self.load("CASES/CASE_001_THE_LAST_RENDER/CASE_CHARTER.json")
        self.assertEqual(case["title"], "THE LAST RENDER")
        self.assertTrue(case["not_demo"])
        self.assertTrue(case["not_experiment"])
        self.assertTrue(case["not_ai_film_label"])
        self.assertEqual(case["case_under_jurisdiction"], "CINEMATICUM")

    def test_pr1_no_engine_no_model_no_media_dirs(self):
        for rel in ["engine", "models.lock", "workflows", "models", "renders", "frames", "exports"]:
            self.assertFalse((ROOT / rel).exists(), rel)

    def test_gitignore_media_boundary(self):
        text = (ROOT / ".gitignore").read_text()
        for pattern in ["*.mp4", "*.mov", "*.wav", "*.safetensors", "*.ckpt", "/models/", "/renders/", "/frames/"]:
            self.assertIn(pattern, text)

    def test_verify_script(self):
        with tempfile.TemporaryDirectory() as d:
            receipt = Path(d) / "receipt.json"
            env = os.environ.copy()
            env["RECEIPT_PATH"] = str(receipt)
            subprocess.run(
                ["bash", "scripts/verify-cinematic-jurisdiction.sh"],
                cwd=ROOT,
                env=env,
                check=True,
            )
            data = json.loads(receipt.read_text())
            self.assertTrue(data["pass"])
            self.assertEqual(data["jurisdiction"], "CINEMATICUM")
            self.assertEqual(data["issued_object"], "ADMISSIBLE_MOTION_PICTURE")

if __name__ == "__main__":
    unittest.main()
