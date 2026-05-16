#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

mp4 = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/cinematicum-backend-selftest/backend_contract_selftest.mp4")

def fail(reason: str):
    print("BACKEND_OUTPUT_CONTRACT_FAIL=true")
    print(f"REASON={reason}")
    print(f"OUTPUT_MP4={mp4}")
    raise SystemExit(1)

if not mp4.exists():
    fail("missing_output_mp4")
if mp4.stat().st_size < 250_000:
    fail("output_too_small_for_realistic_video")

try:
    data = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_format", "-show_streams",
        "-of", "json",
        str(mp4),
    ], text=True))
except Exception as e:
    fail(f"ffprobe_failed:{e}")

streams = data.get("streams", [])
video = next((s for s in streams if s.get("codec_type") == "video"), None)
if not video:
    fail("missing_video_stream")

width = int(video.get("width") or 0)
height = int(video.get("height") or 0)
duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)

if width < 1280 or height < 720:
    fail(f"resolution_below_realistic_floor:{width}x{height}")
if duration < 2.0:
    fail(f"duration_too_short:{duration}")
if video.get("codec_name") not in {"h264", "hevc", "prores", "vp9", "av1"}:
    fail(f"unexpected_video_codec:{video.get('codec_name')}")

print("BACKEND_OUTPUT_CONTRACT_PASS=true")
print(f"OUTPUT_MP4={mp4}")
print(f"WIDTH={width}")
print(f"HEIGHT={height}")
print(f"DURATION_SECONDS={duration:.3f}")
print(f"SIZE_BYTES={mp4.stat().st_size}")
