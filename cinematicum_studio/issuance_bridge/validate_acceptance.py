from __future__ import annotations

import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def validate_cinematic_acceptance(case_id: str) -> tuple[bool, list[str]]:
    film_dir = Path("CASES") / case_id / "FILM"
    missing: list[str] = []

    selected_path = film_dir / "SELECTED_TAKE_RECORD.json"
    if not selected_path.exists():
        missing.append("SELECTED_TAKE_RECORD.json")

    timeline_path = film_dir / "TIMELINE_MANIFEST.json"
    if not timeline_path.exists():
        missing.append("TIMELINE_MANIFEST.json")

    continuity_path = film_dir / "CONTINUITY_REVIEW_RECORD.json"
    if not continuity_path.exists():
        missing.append("CONTINUITY_REVIEW_RECORD.json")
    else:
        continuity = _load_json(continuity_path)
        if continuity.get("accepted") is not True:
            missing.append("CONTINUITY_ACCEPTED")

    director_path = film_dir / "DIRECTORIAL_ACCEPTANCE_RECORD.json"
    if not director_path.exists():
        missing.append("DIRECTORIAL_ACCEPTANCE_RECORD.json")
    else:
        director = _load_json(director_path)
        if director.get("accepted") is not True:
            missing.append("DIRECTORIAL_ACCEPTANCE_ACCEPTED")

    return (len(missing) == 0, missing)
