import subprocess
import unittest
from pathlib import Path


class TestReleaseCandidateReadyStateAdvancementDecisionRecord(unittest.TestCase):
    def test_decision_record_verifier_passes_and_does_not_mutate_state(self):
        result = subprocess.run(
            ["bash", "scripts/verify-release-candidate-ready-state-advancement-decision-record.sh"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        stdout = result.stdout

        required = [
            "CINEMATICUM RELEASE CANDIDATE READY STATE ADVANCEMENT DECISION RECORD: PASS",
            "DECISION_OBJECT=RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_DECISION_RECORD",
            "DECISION_ID=DEC_001_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT",
            "REQUEST_OBJECT=RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST",
            "REQUEST_ID=REQ_001_RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_REQUEST",
            "REQUESTED_NEXT_STATE=RELEASE_CANDIDATE_READY",
            "REQUIRED_PRIOR_OBJECT=RELEASE_CANDIDATE_TERMINAL_CLOSURE_RECORD",
            "DECISION_ACCEPTS_REQUEST=true",
            "DECISION_AUTHORIZES_STATE_MUTATION=true",
            "AUTHORITY_SATISFIED_FOR_TRANSITION=true",
            "STATE_MUTATION_RECORD_REQUIRED_BEFORE_CURRENT_STATE_INDEX_CHANGE=true",
            "AUTHORITY_SATISFIED=false",
            "MAY_ADVANCE_NOW=false",
            "RELEASE_CANDIDATE_READY=false",
            "ISSUED=false",
            "MEDIA_PRESENT=false",
            "CURRENT_STATE_UNCHANGED=true",
            "NEXT_REQUIRED_OBJECT=RELEASE_CANDIDATE_READY_STATE_ADVANCEMENT_EXECUTION_RECORD",
        ]
        for line in required:
            self.assertIn(line, stdout)


if __name__ == "__main__":
    unittest.main()
