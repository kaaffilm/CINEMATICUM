#!/usr/bin/env python3
from pathlib import Path
import json
import shutil
import subprocess
import sys

ROOT = Path.cwd()
FILM = "THE_LAST_RENDER"
SHOTLIST = ROOT / "production" / FILM / "shots" / "shotlist.json"
SRC = ROOT / "source" / "films" / FILM / "shots"

ffprobe = shutil.which("ffprobe")
if not ffprobe:
    print("SOURCE_SHOT_QC_FAIL=true")
    print("FFPROBE_REQUIRED=true")
    sys.exit(1)

shots = json.loads(SHOTLIST.read_text())["shots"]

missing = []
bad = []

for shot in shots:
    filename = shot.get("filename", f"{shot['id']}.mp4")
    path = SRC / filename

    if not path.exists():
        missing.append(filename)
        continue

    try:
        info = json.loads(subprocess.check_output([
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration,size:stream=codec_type,width,height,codec_name",
            "-of", "json",
            str(path)
        ], text=True))
    except subprocess.CalledProcessError:
        bad.append(f"{filename}:ffprobe_failed")
        continue

    video = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    if not video:
        bad.append(f"{filename}:no_video_stream")
        continue

    width = int(video[0].get("width", 0))
    height = int(video[0].get("height", 0))
    duration = float(info.get("format", {}).get("duration", 0))
    size = int(info.get("format", {}).get("size", 0))

    if width < 1280 or height < 720:
        bad.append(f"{filename}:resolution_too_low:{width}x{height}")

    if duration < max(1.0, float(shot["duration"]) * 0.65):
        bad.append(f"{filename}:duration_too_short:{duration:.2f}")

    if size < 250000:
        bad.append(f"{filename}:suspiciously_small:{size}")

if missing:
    print("SOURCE_SHOT_QC_FAIL=true")
    print("MISSING_SOURCE_SHOTS=" + ",".join(missing))
    print("PUT_MP4S_HERE=source/films/THE_LAST_RENDER/shots/")
    sys.exit(1)

if bad:
    print("SOURCE_SHOT_QC_FAIL=true")
    print("BAD_SOURCE_SHOTS=" + ",".join(bad))
    sys.exit(1)

print("SOURCE_SHOT_QC_PASS=true")
print(f"SOURCE_SHOT_COUNT={len(shots)}")
