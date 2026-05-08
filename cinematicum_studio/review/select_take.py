from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.core.db import connect


def select_take(case_id: str, shot_id: str, take_id: str) -> Path:
    conn = connect()
    try:
        take = conn.execute(
            "SELECT * FROM takes WHERE case_id=? AND shot_id=? AND id=?",
            (case_id, shot_id, take_id),
        ).fetchone()
        if not take:
            raise ValueError(f"Take not found: {take_id}")

        conn.execute(
            "INSERT OR REPLACE INTO selected_takes (shot_id, take_id, case_id) VALUES (?, ?, ?)",
            (shot_id, take_id, case_id),
        )
        conn.execute(
            "UPDATE takes SET status='SELECTED' WHERE id=?",
            (take_id,),
        )
        conn.commit()

        rows = conn.execute(
            "SELECT st.shot_id, st.take_id, t.file_path, t.sha256 FROM selected_takes st "
            "JOIN takes t ON t.id = st.take_id WHERE st.case_id=? ORDER BY st.shot_id",
            (case_id,),
        ).fetchall()
    finally:
        conn.close()

    record = {
        "case_id": case_id,
        "selected_takes": [dict(r) for r in rows],
    }

    path = Path("CASES") / case_id / "FILM" / "SELECTED_TAKE_RECORD.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path
