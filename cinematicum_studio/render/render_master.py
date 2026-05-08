from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cinematicum_studio.media.hash import sha256_file


def render_master(case_id: str, version: str = "v001") -> Path:
    timeline_manifest_path = Path("CASES") / case_id / "FILM" / "TIMELINE_MANIFEST.json"
    if not timeline_manifest_path.exists():
        raise RuntimeError("TIMELINE_MANIFEST.json missing. Build timeline first.")

    timeline_manifest = json.loads(timeline_manifest_path.read_text())
    items = timeline_manifest["items"]
    if not items:
        raise RuntimeError("Timeline has no items.")

    render_dir = Path(".cinematicum_media") / case_id / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)

    concat_path = render_dir / f"{case_id}_{version}_concat.txt"
    concat_path.write_text(
        "".join(f"file '{Path(item['file_path']).resolve()}'\n" for item in items)
    )

    output = render_dir / f"THE_LAST_RENDER_{version}.mp4"

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(output),
    ]

    subprocess.run(cmd, check=True)

    digest = sha256_file(output)

    manifest = {
        "case_id": case_id,
        "title": "THE LAST RENDER",
        "version": version,
        "file_path": str(output),
        "sha256": digest,
        "timeline": str(Path("CASES") / case_id / "FILM" / "TIMELINE.otio"),
        "final_master_present": True
    }

    manifest_path = Path("CASES") / case_id / "FILM" / "FINAL_MASTER_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    return output
