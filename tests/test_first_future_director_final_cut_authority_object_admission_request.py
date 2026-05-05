import subprocess
import unittest
from pathlib import Path


class FirstFutureDirectorFinalCutAuthorityObjectAdmissionRequestTest(unittest.TestCase):
    def test_verifier_passes_and_preserves_zero_snapshot(self):
        script = Path("scripts/verify-first-future-director-final-cut-authority-object-admission-request.sh")
        self.assertTrue(script.exists())

        result = subprocess.run(
            ["bash", str(script)],
            check=True,
            text=True,
            capture_output=True,
        )

        out = result.stdout
        self.assertIn(
            "CINEMATICUM FIRST FUTURE DIRECTOR FINAL CUT AUTHORITY OBJECT ADMISSION REQUEST: PASS",
            out,
        )
        self.assertIn("AUTHORITY_SLOT_ID=director_final_cut_authority", out)
        self.assertIn("AUTHORITY_OBJECT=DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT", out)
        self.assertIn("REQUEST_TARGETS_FUTURE_SNAPSHOT=true", out)
        self.assertIn("REQUEST_DOES_NOT_MUTATE_CURRENT_ZERO_SNAPSHOT=true", out)
        self.assertIn("FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW=false", out)
        self.assertIn("AUTHORITY_SATISFIED=false", out)
        self.assertIn("MAY_ADVANCE_NOW=false", out)
        self.assertIn("RELEASE_CANDIDATE_READY=false", out)
        self.assertIn("ISSUED=false", out)
        self.assertIn("MEDIA_PRESENT=false", out)


if __name__ == "__main__":
    unittest.main()
