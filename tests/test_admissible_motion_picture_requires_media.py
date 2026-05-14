from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    "node_modules", "dist", "build"
}

TEXT_EXTS = {
    ".py", ".sh", ".md", ".txt", ".json", ".yml", ".yaml"
}

SELF = Path(__file__).resolve()


def iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == SELF:
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix not in TEXT_EXTS:
            continue
        yield path


def test_admissible_motion_picture_cannot_be_issued_without_media():
    bad = []

    issued_token = "ADMISSIBLE_MOTION_PICTURE_" + "ISSUED=true"
    issued_json = '"admissible_motion_picture_' + 'issued": true'
    media_false_token = "MEDIA_" + "PRESENT=false"
    media_false_json = '"media_' + 'present": false'

    for path in iter_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")

        has_admissible_issued = issued_token in text or issued_json in text
        has_media_absent = media_false_token in text or media_false_json in text

        if has_admissible_issued and has_media_absent:
            bad.append(str(path.relative_to(ROOT)))

    assert not bad, (
        "Forbidden CINEMATICUM issuance state: admissible motion picture "
        "issued while media/audience body is absent: " + ", ".join(bad)
    )
