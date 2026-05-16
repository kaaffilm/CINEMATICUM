#!/usr/bin/env python3
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
FILM = "THE_LAST_RENDER"
SHOTLIST = ROOT / "production" / FILM / "shots" / "shotlist.json"
PROMPTS = ROOT / "production" / FILM / "prompts"
OUT = ROOT / "source" / "films" / FILM / "shots"

def fail(msg: str, code: int = 1):
    print(msg)
    raise SystemExit(code)

if not SHOTLIST.exists():
    fail(f"SHOTLIST_MISSING={SHOTLIST}")

backend = os.environ.get("VIDEO_GEN_COMMAND", "").strip()
if not backend:
    print("SOURCE_SHOT_GENERATION_REFUSED=true")
    print("REASON=VIDEO_GEN_COMMAND_NOT_SET")
    print("THIS_STACK_DOES_NOT_FAKE_REALISTIC_FILM=true")
    print("SET_BACKEND_EXAMPLE=VIDEO_GEN_COMMAND='your_real_video_backend_command' make source-shots")
    print(f"OUTPUT_DIR={OUT}")
    raise SystemExit(1)

data = json.loads(SHOTLIST.read_text(encoding="utf-8"))
shots = data.get("shots", data)
OUT.mkdir(parents=True, exist_ok=True)

missing_prompt = []
failed = []

for shot in shots:
    filename = shot.get("file") or shot.get("filename") or shot.get("source") or shot.get("path") or f"{shot['id']}.mp4"
    shot_id = Path(filename).stem
    prompt_file = PROMPTS / f"{shot_id}.json"
    out_file = OUT / filename

    if out_file.exists() and out_file.stat().st_size > 100_000:
        print(f"SOURCE_SHOT_ALREADY_PRESENT={out_file}")
        continue

    if not prompt_file.exists():
        missing_prompt.append(str(prompt_file))
        continue

    prompt_json = str(prompt_file)
    out_path = str(out_file)

    env = os.environ.copy()
    env["CINEMATICUM_SHOT_ID"] = shot_id
    env["CINEMATICUM_PROMPT_JSON"] = prompt_json
    env["CINEMATICUM_OUTPUT_MP4"] = out_path
    env["CINEMATICUM_FILM"] = FILM

    cmd = shlex.split(backend)
    print(f"GENERATE_SOURCE_SHOT={filename}")
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        failed.append(filename)
        continue

    if not out_file.exists() or out_file.stat().st_size <= 100_000:
        failed.append(filename)

if missing_prompt:
    print("SOURCE_SHOT_GENERATION_FAIL=true")
    print("MISSING_PROMPTS=" + ",".join(missing_prompt))
    raise SystemExit(1)

if failed:
    print("SOURCE_SHOT_GENERATION_FAIL=true")
    print("FAILED_SHOTS=" + ",".join(failed))
    raise SystemExit(1)

print("SOURCE_SHOTS_GENERATED=true")
print(f"OUTPUT_DIR={OUT}")
