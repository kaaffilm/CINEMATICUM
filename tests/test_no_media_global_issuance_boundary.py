import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SKIP_DIR_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
}

FINAL_MEDIA_ISSUANCE_TRUE_KEYS = {
    "admissible_motion_picture_issued",
    "motion_picture_issued",
    "motion_picture_media_issuance_ready",
    "media_issued",
    "media_admitted",
}

PROTOCOL_FILM_CONTEXT_KEYS = {
    "protocol_issued",
    "protocol_perimeter_issued",
    "protocol_film_issued",
}

MEDIA_ABSENCE_KEYS = {
    "media_present",
    "media_payload_present",
    "raw_media_in_git",
    "motion_picture_media_issuance_ready",
}


def iter_json_files():
    for path in ROOT.rglob("*.json"):
        if any(part in SKIP_DIR_PARTS for part in path.parts):
            continue
        yield path


def walk_json(value, path):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from walk_json(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_json(child, f"{path}[{index}]")


def hash_bound_external_media_present(obj):
    media_hash = (
        obj.get("media_sha256")
        or obj.get("motion_picture_media_sha256")
        or obj.get("hash_bound_motion_picture_media_sha256")
    )

    return (
        obj.get("media_present") is True
        and obj.get("raw_media_stored_in_git") is False
        and isinstance(media_hash, str)
        and bool(media_hash)
        and (
            obj.get("object") == "MOTION_PICTURE_MEDIA_ADMISSION_RECORD"
            or bool(obj.get("motion_picture_media_admission_record"))
            or obj.get("issued_object") == "HASH_BOUND_MOTION_PICTURE_MEDIA"
            or obj.get("status") == "terminal_issued"
        )
    )


def media_absent(obj):
    if hash_bound_external_media_present(obj):
        return False
    return any(obj.get(key) is False for key in MEDIA_ABSENCE_KEYS)


def is_protocol_film_issuance_context(obj):
    return any(obj.get(key) is True for key in PROTOCOL_FILM_CONTEXT_KEYS)


def collect_violations():
    violations = []

    for path in iter_json_files():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        for json_path, obj in walk_json(data, "$"):
            if not media_absent(obj):
                continue

            # Generic "issued" is permitted only inside explicit protocol-film
            # issuance context. It is not permitted to stand in for media issuance.

            for key in FINAL_MEDIA_ISSUANCE_TRUE_KEYS:
                if obj.get(key) is True:
                    violations.append(
                        f"{path}:{json_path}: {key}=true while media boundary is false"
                    )

    return violations


class TestNoMediaGlobalIssuanceBoundary(unittest.TestCase):
    def test_no_media_surface_may_claim_final_motion_picture_issuance(self):
        self.assertEqual([], collect_violations())


if __name__ == "__main__":
    unittest.main()
