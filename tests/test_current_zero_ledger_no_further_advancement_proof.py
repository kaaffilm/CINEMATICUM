import subprocess
import unittest


class CurrentZeroLedgerNoFurtherAdvancementProofTest(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-current-zero-ledger-no-further-advancement-proof.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM CURRENT ZERO LEDGER NO FURTHER ADVANCEMENT PROOF: PASS",
            result.stdout,
        )

    def test_proof_is_non_advancing(self):
        result = subprocess.run(
            ["bash", "scripts/verify-current-zero-ledger-no-further-advancement-proof.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        out = result.stdout
        self.assertIn("PROOF_DOES_NOT_ADVANCE_STATE=true", out)
        self.assertIn("PROOF_DOES_NOT_ISSUE_MOTION_PICTURE=true", out)
        self.assertIn("PROOF_DOES_NOT_ADMIT_MEDIA=true", out)
        self.assertIn("MAY_ADVANCE_NOW=false", out)
        self.assertIn("ISSUED=false", out)
        self.assertIn("MEDIA_PRESENT=false", out)


if __name__ == "__main__":
    unittest.main()
