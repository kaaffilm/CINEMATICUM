#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CINEMATICUM_OUTPUT_MP4", ""))

def fail(reason):
    print("BACKEND_OUTPUT_CONTRACT_FAIL=true")
    print(f"REASON={reason}")
    print(f"OUTPUT_MP4={p}")
    raise SystemExit(1)

if not str(p):
    fail("output_path_not_set")
if not p.exists():
    fail("missing_output_mp4")
if p.stat().st_size < 1_000_000:
    fail(f"output_too_small:{p.stat().st_size}")

probe = subprocess.run(
    ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(p)],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

if probe.returncode:
    fail("ffprobe_failed")

data = json.loads(probe.stdout)
duration = float(data.get("format", {}).get("duration") or 0)
if duration < 2:
    fail(f"duration_too_short:{duration}")

videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
if not videos:
    fail("no_video_stream")

v = videos[0]
if int(v.get("width") or 0) < 512 or int(v.get("height") or 0) < 288:
    fail(f"resolution_too_low:{v.get('width')}x{v.get('height')}")

print("BACKEND_OUTPUT_CONTRACT_PASS=true")
print(f"OUTPUT_MP4={p}")
print(f"DURATION_SECONDS={duration}")
print(f"SIZE_BYTES={p.stat().st_size}")
