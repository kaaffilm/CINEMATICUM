from __future__ import annotations

import json
import uuid
from pathlib import Path

from cinematicum_studio.core.db import connect
from cinematicum_studio.generation.adapters.command import CommandVideoAdapter
from cinematicum_studio.media.hash import sha256_file


CASE_ROOT = Path("CASES/CASE_001_THE_LAST_RENDER/FILM")
MEDIA_ROOT = Path(".cinematicum_media")


def load_shot_graph(case_id: str) -> dict:
    path = Path("CASES") / case_id / "FILM" / "SHOT_GRAPH.json"
    return json.loads(path.read_text())


def generate_shot(case_id: str, shot_id: str, takes: int, backend: str = "command") -> list[dict]:
    if backend != "command":
        raise ValueError("Only backend='command' is wired now. Add real named adapters next.")

    graph = load_shot_graph(case_id)
    shots = {s["id"]: s for s in graph["shots"]}
    if shot_id not in shots:
        raise ValueError(f"Unknown shot_id: {shot_id}")

    shot = shots[shot_id]
    adapter = CommandVideoAdapter()
    out_dir = MEDIA_ROOT / case_id / "generated" / shot_id
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    conn = connect()

    try:
        for i in range(1, takes + 1):
            take_id = f"{shot_id}_TAKE_{i:03d}"
            job_id = f"JOB_{uuid.uuid4().hex[:12]}"
            out_path = out_dir / f"TAKE_{i:03d}.mp4"

            conn.execute(
                "INSERT OR REPLACE INTO generation_jobs "
                "(id, case_id, shot_id, backend, model, status, prompt, seed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (job_id, case_id, shot_id, backend, None, "RUNNING", shot["prompt"], i),
            )
            conn.commit()

            result = adapter.generate(
                prompt=shot["prompt"],
                duration=int(shot["duration"]),
                output_path=str(out_path),
                seed=i,
            )

            if not out_path.exists():
                raise RuntimeError(f"Generator did not create {out_path}")

            digest = sha256_file(out_path)

            conn.execute(
                "INSERT OR REPLACE INTO takes "
                "(id, case_id, shot_id, job_id, backend, model, prompt, seed, file_path, sha256, duration, width, height, fps, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    take_id,
                    case_id,
                    shot_id,
                    job_id,
                    result.backend,
                    result.model,
                    shot["prompt"],
                    i,
                    str(out_path),
                    digest,
                    result.duration,
                    result.width,
                    result.height,
                    result.fps,
                    "GENERATED",
                ),
            )
            conn.execute(
                "UPDATE generation_jobs SET status=? WHERE id=?",
                ("COMPLETE", job_id),
            )
            conn.commit()

            results.append(
                {
                    "take_id": take_id,
                    "shot_id": shot_id,
                    "file_path": str(out_path),
                    "sha256": digest,
                    "backend": result.backend,
                    "model": result.model,
                    "prompt": shot["prompt"],
                    "seed": i,
                    "status": "GENERATED",
                }
            )
    finally:
        conn.close()

    write_take_ledger(case_id)
    return results


def generate_all(case_id: str, takes_per_shot: int, backend: str = "command") -> None:
    graph = load_shot_graph(case_id)
    for shot in graph["shots"]:
        generate_shot(case_id, shot["id"], takes_per_shot, backend=backend)


def write_take_ledger(case_id: str) -> Path:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM takes WHERE case_id=? ORDER BY shot_id, id",
            (case_id,),
        ).fetchall()
    finally:
        conn.close()

    by_shot: dict[str, list[dict]] = {}
    for row in rows:
        by_shot.setdefault(row["shot_id"], []).append(dict(row))

    ledger = {
        "case_id": case_id,
        "shots": [
            {
                "shot_id": shot_id,
                "takes": takes,
            }
            for shot_id, takes in sorted(by_shot.items())
        ],
    }

    path = Path("CASES") / case_id / "FILM" / "TAKE_LEDGER.json"
    path.write_text(json.dumps(ledger, indent=2) + "\n")
    return path
