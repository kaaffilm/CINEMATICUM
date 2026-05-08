from __future__ import annotations

import json
from pathlib import Path


def validate_master_ready(case_id: str) -> tuple[bool, list[str]]:
    base = Path("CASES") / case_id / "FILM"

    required = {
        "SHOT_GRAPH.json": base / "SHOT_GRAPH.json",
        "TAKE_LEDGER.json": base / "TAKE_LEDGER.json",
        "SELECTED_TAKE_RECORD.json": base / "SELECTED_TAKE_RECORD.json",
        "TIMELINE.otio": base / "TIMELINE.otio",
        "TIMELINE_MANIFEST.json": base / "TIMELINE_MANIFEST.json",
        "FINAL_MASTER_MANIFEST.json": base / "FINAL_MASTER_MANIFEST.json"
    }

    missing = [name for name, path in required.items() if not path.exists()]

    final_manifest = required["FINAL_MASTER_MANIFEST.json"]
    if final_manifest.exists():
        data = json.loads(final_manifest.read_text())
        media_path = Path(data["file_path"])
        if not media_path.exists():
            missing.append("FINAL_MASTER_MEDIA_FILE")
        if not data.get("sha256"):
            missing.append("FINAL_MASTER_SHA256")

    return (len(missing) == 0, missing)
