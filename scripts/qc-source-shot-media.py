#!/usr/bin/env python3
import hashlib
import json
import math
import subprocess
from pathlib import Path

FILM = "THE_LAST_RENDER"
SHOTLIST = Path(f"production/{FILM}/shots/shotlist.json")
SOURCE = Path(f"source/films/{FILM}/shots")

MIN_WIDTH = 1280
MIN_HEIGHT = 720
MIN_DURATION_SECONDS = 2.0
MIN_BYTES_PER_SECOND = 75_000
MIN_MOTION_SCORE = 0.35
MIN_COMPLEXITY_SCORE = 6.0

LOW_MOTION_ALLOWED = (
    "blackout",
    "silence",
    "lockoff",
    "dead_screen",
)

def load_shots():
    data = json.loads(SHOTLIST.read_text())
    shots = data.get("shots", data)
    out = []
    for s in shots:
        file = s.get("file") or s.get("filename") or s.get("source") or s.get("path") or (s.get("id", "") + ".mp4")
        expected_duration = s.get("duration_seconds") or s.get("duration") or s.get("seconds")
        out.append({
            "id": s.get("id") or Path(file).stem,
            "file": file,
            "expected_duration": float(expected_duration) if expected_duration else None,
        })
    return out

def ffprobe(path: Path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_format", "-show_streams",
        "-of", "json",
        str(path),
    ], text=True))

def frame_metrics(path: Path):
    frame_w, frame_h = 160, 90
    frame_size = frame_w * frame_h
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error",
        "-i", str(path),
        "-vf", f"fps=1,scale={frame_w}:{frame_h}:flags=bilinear,format=gray",
        "-frames:v", "6",
        "-f", "rawvideo",
        "pipe:1",
    ], timeout=30)

    count = len(raw) // frame_size
    if count < 2:
        return 0.0, 0.0

    frames = [raw[i * frame_size:(i + 1) * frame_size] for i in range(count)]

    complexities = []
    for fr in frames:
        n = len(fr)
        mean = sum(fr) / n
        var = sum((b - mean) * (b - mean) for b in fr) / n
        complexities.append(math.sqrt(var))

    motions = []
    for a, b in zip(frames, frames[1:]):
        motions.append(sum(abs(x - y) for x, y in zip(a, b)) / frame_size)

    return max(motions), sum(complexities) / len(complexities)

def fail(failures):
    print("SOURCE_SHOT_MEDIA_QC_FAIL=true")
    for f in failures:
        print(f"FAIL={f}")
    raise SystemExit(1)

shots = load_shots()
failures = []
hashes = {}

for shot in shots:
    file = shot["file"]
    shot_id = shot["id"]
    path = SOURCE / file

    if not path.exists():
        failures.append(f"{file}:missing")
        continue

    if path.suffix.lower() != ".mp4":
        failures.append(f"{file}:not_mp4")
        continue

    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha in hashes:
        failures.append(f"{file}:duplicate_bytes_of:{hashes[sha]}")
    hashes[sha] = file

    try:
        data = ffprobe(path)
    except Exception as e:
        failures.append(f"{file}:ffprobe_failed:{e}")
        continue

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        failures.append(f"{file}:missing_video_stream")
        continue

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    size = path.stat().st_size

    if width < MIN_WIDTH or height < MIN_HEIGHT:
        failures.append(f"{file}:resolution_below_floor:{width}x{height}")

    expected = shot["expected_duration"]
    if expected is not None:
        if duration < expected * 0.75:
            failures.append(f"{file}:duration_below_expected:{duration:.3f}<expected_{expected:.3f}")
    elif duration < MIN_DURATION_SECONDS:
        failures.append(f"{file}:duration_too_short:{duration:.3f}")

    if duration > 0 and size / duration < MIN_BYTES_PER_SECOND:
        failures.append(f"{file}:bitrate_too_low_for_realistic_source:{int(size/duration)}_bytes_per_second")

    try:
        motion, complexity = frame_metrics(path)
    except Exception as e:
        failures.append(f"{file}:frame_metric_failed:{e}")
        continue

    low_motion_allowed = any(token in file for token in LOW_MOTION_ALLOWED)
    if not low_motion_allowed and motion < MIN_MOTION_SCORE:
        failures.append(f"{file}:motion_too_low:{motion:.3f}")

    if complexity < MIN_COMPLEXITY_SCORE:
        failures.append(f"{file}:visual_complexity_too_low:{complexity:.3f}")

if failures:
    fail(failures)

print("SOURCE_SHOT_MEDIA_QC_PASS=true")
print(f"SHOT_MEDIA_COUNT={len(shots)}")
print(f"MIN_WIDTH={MIN_WIDTH}")
print(f"MIN_HEIGHT={MIN_HEIGHT}")
print(f"UNIQUE_SOURCE_SHOTS={len(hashes)}")
