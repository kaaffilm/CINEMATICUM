#!/usr/bin/env python3
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path.cwd()
FILM = "THE_LAST_RENDER"
SHOTLIST = ROOT / "production" / FILM / "shots" / "shotlist.json"
PROMPTS = ROOT / "production" / FILM / "prompts"
OUT = ROOT / "source" / "films" / FILM / "shots"

PLACEHOLDERS = {
    "",
    "your_real_video_backend_command",
    "your_generator_command_here",
    "real_video_backend",
    "your_backend",
}

backend = os.environ.get("VIDEO_GEN_COMMAND", "").strip()

if backend in PLACEHOLDERS:
    print("SOURCE_SHOT_GENERATION_REFUSED=true")
    print("REASON=REAL_VIDEO_BACKEND_NOT_CONFIGURED")
    print("THIS_STACK_DOES_NOT_FAKE_REALISTIC_FILM=true")
    print("REQUIRED=Set VIDEO_GEN_COMMAND to an actual executable wrapper")
    print("EXAMPLE=VIDEO_GEN_COMMAND=./scripts/backends/your-real-backend.sh make source-shots")
    print(f"OUTPUT_DIR={OUT}")
    raise SystemExit(1)

cmd = shlex.split(backend)
if not cmd:
    print("SOURCE_SHOT_GENERATION_REFUSED=true")
    print("REASON=EMPTY_BACKEND_COMMAND")
    raise SystemExit(1)

exe = cmd[0]
if "/" in exe:
    exe_path = Path(exe)
    if not exe_path.exists():
        print("SOURCE_SHOT_GENERATION_REFUSED=true")
        print(f"REASON=BACKEND_EXECUTABLE_NOT_FOUND:{exe}")
        raise SystemExit(1)
    if not os.access(exe_path, os.X_OK):
        print("SOURCE_SHOT_GENERATION_REFUSED=true")
        print(f"REASON=BACKEND_NOT_EXECUTABLE:{exe}")
        raise SystemExit(1)
else:
    if shutil.which(exe) is None:
        print("SOURCE_SHOT_GENERATION_REFUSED=true")
        print(f"REASON=BACKEND_EXECUTABLE_NOT_FOUND:{exe}")
        raise SystemExit(1)

if not SHOTLIST.exists():
    print("SOURCE_SHOT_GENERATION_REFUSED=true")
    print(f"REASON=SHOTLIST_MISSING:{SHOTLIST}")
    raise SystemExit(1)

data = json.loads(SHOTLIST.read_text(encoding="utf-8"))
shots = data.get("shots", data)
OUT.mkdir(parents=True, exist_ok=True)

for index, shot in enumerate(shots, start=1):
    shot_id = shot.get("id")
    filename = shot.get("file") or shot.get("filename") or f"{shot_id}.mp4"
    prompt_json = PROMPTS / f"{shot_id}.json"
    output_mp4 = OUT / filename

    if not shot_id:
        print("SOURCE_SHOT_GENERATION_FAIL=true")
        print(f"REASON=SHOT_ID_MISSING_AT_INDEX:{index}")
        raise SystemExit(1)

    if not prompt_json.exists():
        print("SOURCE_SHOT_GENERATION_FAIL=true")
        print(f"REASON=PROMPT_JSON_MISSING:{prompt_json}")
        raise SystemExit(1)

    env = os.environ.copy()
    env.update({
        "CINEMATICUM_FILM": FILM,
        "CINEMATICUM_SHOT_ID": shot_id,
        "CINEMATICUM_SHOT_INDEX": str(index),
        "CINEMATICUM_PROMPT_JSON": str(prompt_json),
        "CINEMATICUM_OUTPUT_MP4": str(output_mp4),
    })

    print(f"GENERATE_SOURCE_SHOT={filename}")
    result = subprocess.run(cmd, env=env)

    if result.returncode != 0:
        print("SOURCE_SHOT_GENERATION_FAIL=true")
        print(f"FAILED_SHOT={filename}")
        print(f"FAILED_BACKEND={' '.join(cmd)}")
        print("FAIL_FAST=true")
        raise SystemExit(result.returncode)

    if not output_mp4.exists():
        print("SOURCE_SHOT_GENERATION_FAIL=true")
        print(f"REASON=BACKEND_DID_NOT_WRITE_OUTPUT:{output_mp4}")
        raise SystemExit(1)

    if output_mp4.stat().st_size <= 0:
        print("SOURCE_SHOT_GENERATION_FAIL=true")
        print(f"REASON=BACKEND_WROTE_EMPTY_OUTPUT:{output_mp4}")
        raise SystemExit(1)

    print(f"SOURCE_SHOT_READY={filename}")

print("SOURCE_SHOT_GENERATION_PASS=true")
print(f"SOURCE_SHOT_DIR={OUT}")
