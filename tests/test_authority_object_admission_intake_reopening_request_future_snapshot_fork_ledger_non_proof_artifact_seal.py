import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
FULL = 'AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_PROOF_ARTIFACT_SEAL'
LABEL = 'NON-PROOF-ARTIFACT'

class TestFutureForkLedgerNonProofArtifactSeal(unittest.TestCase):
    def test_status_contract(self):
        status = json.loads(Path(f"CASES/CASE_001_THE_LAST_RENDER/{FULL}_STATUS.json").read_text())
        self.assertEqual(status["current_state"], TARGET)
        self.assertFalse(status["release_candidate_ready"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])
        self.assertFalse(status["may_advance_now"])

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-" + FULL.lower().replace("_", "-") + ".sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn(f"{LABEL}: PASS", out)
        self.assertIn("CURRENT_STATE=" + TARGET, out)

if __name__ == "__main__":
    unittest.main()
