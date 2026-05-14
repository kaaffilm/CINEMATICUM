import json
import subprocess
import unittest
from pathlib import Path

OLD = 'OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED'
TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'

class TestCurrentStateIndexAdvancementRecord(unittest.TestCase):
    def test_record(self):
        data = json.loads(Path('CASES/CASE_001_THE_LAST_RENDER/CURRENT_STATE_INDEX_ADVANCEMENT_RECORD/CURRENT_STATE_INDEX_ADVANCEMENT_RECORD.json').read_text())
        self.assertEqual(data['from_state'], OLD)
        self.assertEqual(data['to_state'], TARGET)
        self.assertFalse(data['release_candidate_ready'])
        self.assertFalse(data['issued'])
        self.assertFalse(data['media_present'])
        self.assertFalse(data['outsider_replay_passed'])
        self.assertEqual(data['next_required_object'], 'RELEASE_CANDIDATE_GAP_LEDGER')

    def test_verifier(self):
        out = subprocess.run(['bash', 'scripts/verify-current-state-index-advancement-record.sh'], check=True, text=True, capture_output=True).stdout
        self.assertIn('CINEMATICUM CURRENT STATE INDEX ADVANCEMENT RECORD: PASS', out)
        self.assertIn(f'TO_STATE={TARGET}', out)

if __name__ == '__main__':
    unittest.main()
