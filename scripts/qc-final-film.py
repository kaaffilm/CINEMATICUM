#!/usr/bin/env python3
from pathlib import Path
import json
import shutil
import subprocess
import sys

ROOT = Path.cwd()
FILM = "THE_LAST_RENDER"
FINAL = ROOT / "dist" / "films" / FILM / f"{FILM}.mp4"
MANIFEST = ROOT / "dist" / "films" / FILM / f"{FILM}_manifest.json"

ffprobe = shutil.which("ffprobe")
if not ffprobe:
    print("FINAL_FILM_QC_FAIL=true")
    print("FFPROBE_REQUIRED=true")
    sys.exit(1)

if not FINAL.exists():
    print("FINAL_FILM_QC_FAIL=true")
    print(f"MISSING_FINAL={FINAL}")
    sys.exit(1)

if not MANIFEST.exists():
    print("FINAL_FILM_QC_FAIL=true")
    print(f"MISSING_MANIFEST={MANIFEST}")
    sys.exit(1)

manifest = json.loads(MANIFEST.read_text())

if manifest.get("toy_renderer_allowed") is not False:
    print("FINAL_FILM_QC_FAIL=true")
    print("toy_renderer_allowed must be false")
    sys.exit(1)

if manifest.get("artifact_class") != "REALISTIC_SOURCE_SHOT_FILM":
    print("FINAL_FILM_QC_FAIL=true")
    print("WRONG_ARTIFACT_CLASS=" + str(manifest.get("artifact_class")))
    sys.exit(1)

info = json.loads(subprocess.check_output([
    ffprobe,
    "-v", "error",
    "-show_entries", "format=duration,size:stream=codec_type,width,height",
    "-of", "json",
    str(FINAL)
], text=True))

video = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]

if not video:
    print("FINAL_FILM_QC_FAIL=true")
    print("NO_VIDEO_STREAM=true")
    sys.exit(1)

if not audio:
    print("FINAL_FILM_QC_FAIL=true")
    print("NO_AUDIO_STREAM=true")
    sys.exit(1)

duration = float(info["format"]["duration"])
width = int(video[0].get("width", 0))
height = int(video[0].get("height", 0))

if width < 1280 or height < 720:
    print("FINAL_FILM_QC_FAIL=true")
    print(f"FINAL_RESOLUTION_TOO_LOW={width}x{height}")
    sys.exit(1)

if duration < 70:
    print("FINAL_FILM_QC_FAIL=true")
    print(f"FINAL_DURATION_TOO_SHORT={duration}")
    sys.exit(1)

print("FINAL_FILM_QC_PASS=true")
print(f"DURATION_SECONDS={duration}")
print(f"RESOLUTION={width}x{height}")
print(f"SHOT_COUNT={manifest.get('shot_count')}")
