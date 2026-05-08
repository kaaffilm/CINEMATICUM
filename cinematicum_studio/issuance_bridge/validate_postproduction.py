from __future__ import annotations

import json
from pathlib import Path


CASE_ROOT = Path("CASES")


REQUIRED_RECORDS = {
    "SOUND_MIX_ACCEPTANCE_RECORD.json": "SOUND_MIX_ACCEPTED",
    "COLOR_GRADE_ACCEPTANCE_RECORD.json": "COLOR_GRADE_ACCEPTED",
    "FINAL_CUT_ACCEPTANCE_RECORD.json": "FINAL_CUT_ACCEPTED",
    "PUBLIC_ADMISSIBILITY_VERDICT.json": "PUBLIC_ADMISSIBILITY_VERDICT_ACCEPTED",
}


def validate_postproduction_acceptance(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    for filename, token in REQUIRED_RECORDS.items():
        path = film_dir / filename
        if not path.exists():
            missing.append(filename)
            continue

        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append(token)

    return (len(missing) == 0, missing)
