import json
import pathlib
import re
import stat
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestMasterVerificationManifestClosure(unittest.TestCase):
    def test_closure_matches_current_state(self):
        closure = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(closure["current_state"], "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], "ISSUED_ADMISSIBLE_MOTION_PICTURE")
        self.assertEqual(case["current_state"], "ISSUED_ADMISSIBLE_MOTION_PICTURE")

    def test_manifest_required_scripts_exist_and_are_in_verify_all(self):
        manifest = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json")
        verify_all = (ROOT / "scripts/verify-all.sh").read_text(encoding="utf-8")
        closure = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE.json")
        exempt = set(closure["verify_all_membership_exempt_scripts"])
        self.assertEqual(exempt, {"scripts/verify-all.sh", "scripts/regenerate-object-registry.py"})
        for script in manifest["required_scripts"]:
            path = ROOT / script
            self.assertTrue(path.exists(), script)
            if script not in exempt:
                self.assertIn(script, verify_all)
            if script.startswith("scripts/"):
                self.assertTrue(path.stat().st_mode & stat.S_IXUSR, script)

    def test_manifest_required_tests_exist_and_are_in_verify_all(self):
        manifest = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json")
        verify_all = (ROOT / "scripts/verify-all.sh").read_text(encoding="utf-8")
        for test in manifest["required_unittests"]:
            path = ROOT / test
            self.assertTrue(path.exists(), test)
            self.assertIn(test, verify_all)

    def test_manifest_required_workflows_exist(self):
        manifest = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json")
        workflow_files = list((ROOT / ".github/workflows").glob("*.yml")) + list((ROOT / ".github/workflows").glob("*.yaml"))
        stems = {p.stem for p in workflow_files}
        names = set()
        for path in workflow_files:
            for line in path.read_text(encoding="utf-8").splitlines():
                match = re.match(r"^\s*name:\s*[\"']?([^\"'#]+)[\"']?\s*(?:#.*)?$", line)
                if match:
                    names.add(match.group(1).strip())
                    break
        for workflow in manifest["required_ci_workflows"]:
            self.assertTrue(workflow in stems or workflow in names, workflow)

    def test_closure_assertions_true(self):
        closure = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE.json")
        for key, value in closure["closure_checks"].items():
            self.assertTrue(value, key)

    def test_false_values_remain_false(self):
        closure = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE.json")
        for key in [
            "release_candidate_ready",
            "issued",
            "media_present",
            "generation_present",
            "engine_present",
            "model_present",
            "outsider_replay_passed",
            "admissibility_verdict_present",
            "terminal_closure_present",
        ]:
            self.assertFalse(closure["current_false_values"][key], key)

    def test_closure_doc_is_bounded(self):
        text = (ROOT / "MASTER_VERIFICATION_MANIFEST_CLOSURE.md").read_text(encoding="utf-8")
        self.assertIn("all_required_scripts_exist=true", text)
        self.assertIn("verify_all_self_reference_exempt=true", text)
        self.assertIn("verify_all_membership_exempt_scripts_declared=true", text)
        self.assertIn("registry_generator_exempt_from_verify_all_membership=true", text)
        self.assertIn("all_required_unittests_exist=true", text)
        self.assertIn("all_required_ci_workflows_exist=true", text)
        self.assertIn("does not issue a film", text)
        self.assertIn("does not admit media", text)
        self.assertIn("does not advance state", text)

if __name__ == "__main__":
    unittest.main()
