import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RAW_MEDIA_PAYLOAD_TRUE_FORBIDDEN_KEYS = {
    "raw_media_stored_in_git",
    "media_payload_present",
    "generation_present",
    "engine_present",
    "model_present",
    "model_weight_payload_present",
}

NEGATIVE_PROOF_CONTAINER_KEYS = {
    "proves_absence_of",
    "negative_proof",
    "absence_proof",
}


def walk(obj, path="$", parent_key=None):
    if isinstance(obj, dict):
        yield path, obj, parent_key
        for key, value in obj.items():
            yield from walk(value, f"{path}.{key}", key)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from walk(value, f"{path}[{i}]", parent_key)


class TestNoMediaGlobalIssuanceBoundary(unittest.TestCase):
    def test_no_raw_media_payload_is_claimed_inside_git(self):
        violations = []

        for file_path in ROOT.rglob("*.json"):
            if ".git" in file_path.parts:
                continue
            if "fixtures" in file_path.parts and "rejected" in file_path.parts:
                continue

            try:
                data = json.loads(file_path.read_text())
            except json.JSONDecodeError:
                continue

            for obj_path, obj, parent_key in walk(data):
                if parent_key in NEGATIVE_PROOF_CONTAINER_KEYS:
                    continue

                for key in RAW_MEDIA_PAYLOAD_TRUE_FORBIDDEN_KEYS:
                    if obj.get(key) is True:
                        violations.append(f"{file_path}:{obj_path}: {key}=true")

        self.assertEqual([], violations)

    def test_hash_bound_external_media_issuance_is_allowed_without_raw_git_payload(self):
        seal = json.loads((ROOT / "CINEMATICUM_REPOSITORY_STATUS_SEAL.json").read_text())

        self.assertTrue(seal["issued"])
        self.assertTrue(seal["media_present"])
        self.assertTrue(seal["motion_picture_media_issuance_ready"])
        self.assertFalse(seal["raw_media_stored_in_git"])
