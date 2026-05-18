#!/usr/bin/env python3
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
FILM = "THE_LAST_RENDER"
SHOT_ID = os.environ.get("SHOT_ID", "").strip()

if not SHOT_ID:
    print("ONE_SHOT_BACKEND_REFUSED=true")
    print("REASON=SHOT_ID_NOT_SET")
    print("EXAMPLE=SHOT_ID=001_service_road_rain VIDEO_GEN_COMMAND=/actual/backend make source-shot-one")
    raise SystemExit(1)

cmd_raw = os.environ.get("VIDEO_GEN_COMMAND", "").strip()
if not cmd_raw:
    print("ONE_SHOT_BACKEND_REFUSED=true")
    print("REASON=VIDEO_GEN_COMMAND_NOT_SET")
    raise SystemExit(1)

if cmd_raw in {
    "./scripts/backends/your-real-backend.sh",
    "/absolute/path/to/real/video/backend",
    "/actual/executable/backend",
    "your_real_video_backend_command",
}:
    print("ONE_SHOT_BACKEND_REFUSED=true")
    print("REASON=PLACEHOLDER_BACKEND")
    raise SystemExit(1)

cmd0 = shlex.split(cmd_raw)[0]
if not Path(cmd0).exists() and "/" in cmd0:
    print("ONE_SHOT_BACKEND_REFUSED=true")
    print(f"REASON=BACKEND_EXECUTABLE_NOT_FOUND:{cmd0}")
    raise SystemExit(1)

shotlist_path = ROOT / "production" / FILM / "shots" / "shotlist.json"
shotlist = json.loads(shotlist_path.read_text())
shots = shotlist.get("shots", shotlist)

shot = None
for s in shots:
    sid = s.get("id") or Path(s.get("file", "")).stem
    if sid == SHOT_ID:
        shot = s
        break

if shot is None:
    print("ONE_SHOT_BACKEND_REFUSED=true")
    print(f"REASON=SHOT_ID_NOT_IN_SHOTLIST:{SHOT_ID}")
    raise SystemExit(1)

filename = shot.get("file") or f"{SHOT_ID}.mp4"
prompt_json = ROOT / "production" / FILM / "prompts" / f"{SHOT_ID}.json"
output_mp4 = ROOT / "source" / "films" / FILM / "shots" / filename
output_mp4.parent.mkdir(parents=True, exist_ok=True)

env = os.environ.copy()
env.update({
    "CINEMATICUM_FILM": FILM,
    "CINEMATICUM_SHOT_ID": SHOT_ID,
    "CINEMATICUM_PROMPT_JSON": str(prompt_json),
    "CINEMATICUM_OUTPUT_MP4": str(output_mp4),
})

print(f"GENERATE_ONE_SOURCE_SHOT={filename}")
print(f"PROMPT_JSON={prompt_json}")
print(f"OUTPUT_MP4={output_mp4}")

result = subprocess.run(shlex.split(cmd_raw), env=env)
if result.returncode != 0:
    print("ONE_SHOT_BACKEND_FAIL=true")
    print(f"FAILED_SHOT={filename}")
    raise SystemExit(result.returncode)

if not output_mp4.exists() or output_mp4.stat().st_size < 1_000_000:
    print("ONE_SHOT_BACKEND_FAIL=true")
    print("REASON=backend_did_not_write_substantial_mp4")
    print(f"OUTPUT_MP4={output_mp4}")
    raise SystemExit(1)

print("ONE_SHOT_BACKEND_OUTPUT_CREATED=true")
print(f"OUTPUT_MP4={output_mp4}")
