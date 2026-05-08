from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.core.db import connect


def build_timeline(case_id: str) -> Path:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT sh.id AS shot_id, sh.shot_order, sh.duration, st.take_id, t.file_path, t.sha256 "
            "FROM shots sh "
            "JOIN selected_takes st ON st.shot_id = sh.id "
            "JOIN takes t ON t.id = st.take_id "
            "WHERE sh.case_id=? ORDER BY sh.shot_order",
            (case_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise RuntimeError("No selected takes. Cannot build timeline.")

    timeline = {
        "OTIO_SCHEMA": "Timeline.1",
        "metadata": {
            "case_id": case_id,
            "generated_by": "CINEMATICUM_STUDIO"
        },
        "name": f"{case_id}_TIMELINE",
        "tracks": [
            {
                "OTIO_SCHEMA": "Track.1",
                "name": "V1",
                "kind": "Video",
                "children": [
                    {
                        "OTIO_SCHEMA": "Clip.2",
                        "name": row["shot_id"],
                        "media_reference": {
                            "OTIO_SCHEMA": "ExternalReference.1",
                            "target_url": row["file_path"],
                            "metadata": {
                                "take_id": row["take_id"],
                                "sha256": row["sha256"]
                            }
                        },
                        "source_range": {
                            "OTIO_SCHEMA": "TimeRange.1",
                            "start_time": {
                                "OTIO_SCHEMA": "RationalTime.1",
                                "value": 0,
                                "rate": 24
                            },
                            "duration": {
                                "OTIO_SCHEMA": "RationalTime.1",
                                "value": int(row["duration"]) * 24,
                                "rate": 24
                            }
                        }
                    }
                    for row in rows
                ]
            }
        ]
    }

    path = Path("CASES") / case_id / "FILM" / "TIMELINE.otio"
    path.write_text(json.dumps(timeline, indent=2) + "\n")

    manifest = {
        "case_id": case_id,
        "timeline": str(path),
        "items": [dict(r) for r in rows],
        "timeline_present": true if False else True
    }
    manifest_path = Path("CASES") / case_id / "FILM" / "TIMELINE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    return path
