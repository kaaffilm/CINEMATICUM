import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

PATHS = [
    ROOT / "CASES/CASE_001_THE_LAST_RENDER/RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD/RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD.json",
    ROOT / "CASES/CASE_001_THE_LAST_RENDER/RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD_STATUS.json",
    ROOT / "CINEMATICUM_RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD.json",
    ROOT / "CINEMATICUM_RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD_LAW.json",
]


def load_all():
    merged = {}
    for path in PATHS:
        merged.update(json.loads(path.read_text(encoding="utf-8")))
    return merged


class TestReleaseCandidateTerminalClosureRecord(unittest.TestCase):
    def test_required_files_exist(self):
        for path in PATHS:
            self.assertTrue(path.exists(), f"missing required file: {path}")

    def test_terminal_closure_semantics_present(self):
        merged = load_all()
        self.assertEqual(merged["record_id"], "RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD")
        self.assertTrue(merged["terminal_closure_record_present"])
        self.assertTrue(merged["terminal_closure_present"])
        self.assertEqual(merged["admissibility_verdict_result"], "ADMISSIBLE")
        self.assertEqual(merged["outsider_replay_execution_result"], "PASS")
        self.assertEqual(
            merged["next_required_object"],
            "RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST",
        )

    def test_release_not_advanced_or_issued(self):
        merged = load_all()
        self.assertFalse(merged["release_candidate_ready"])
        self.assertFalse(merged["issued"])
        self.assertFalse(merged["media_present"])

    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-release-candidate-terminal-closure-record.sh"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=True,
        )
        self.assertIn("CINEMATICUM RELEASE CANDIDATE TERMINAL CLOSURE RECORD: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
