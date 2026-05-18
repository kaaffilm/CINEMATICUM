#!/usr/bin/env python3
import json
import math
import subprocess
from pathlib import Path

FILM = "THE_LAST_RENDER"
FINAL = Path(f"dist/films/{FILM}/{FILM}.mp4")
SHOTLIST = Path(f"production/{FILM}/shots/shotlist.json")

MIN_WIDTH = 1280
MIN_HEIGHT = 720
MIN_DURATION_SECONDS = 45.0
MIN_BYTES_PER_SECOND = 100_000
MIN_MOTION_SCORE = 0.25
MIN_COMPLEXITY_SCORE = 7.0

def fail(reason: str):
    print("FINAL_FILM_MEDIA_QC_FAIL=true")
    print(f"REASON={reason}")
    print(f"FINAL={FINAL}")
    raise SystemExit(1)

if not FINAL.exists():
    fail("missing_final_mp4")

if FINAL.stat().st_size < 5_000_000:
    fail("final_file_too_small_for_realistic_film")

try:
    data = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_format", "-show_streams",
        "-of", "json",
        str(FINAL),
    ], text=True))
except Exception as e:
    fail(f"ffprobe_failed:{e}")

streams = data.get("streams", [])
video = next((s for s in streams if s.get("codec_type") == "video"), None)
audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

if not video:
    fail("missing_video_stream")
if not audio:
    fail("missing_audio_stream")

width = int(video.get("width") or 0)
height = int(video.get("height") or 0)
duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
size = FINAL.stat().st_size

if width < MIN_WIDTH or height < MIN_HEIGHT:
    fail(f"resolution_below_floor:{width}x{height}")

if duration < MIN_DURATION_SECONDS:
    fail(f"duration_below_floor:{duration:.3f}")

if duration > 0 and size / duration < MIN_BYTES_PER_SECOND:
    fail(f"bitrate_too_low_for_final:{int(size / duration)}_bytes_per_second")

if SHOTLIST.exists():
    shot_data = json.loads(SHOTLIST.read_text())
    shots = shot_data.get("shots", shot_data)
    expected = 0.0
    counted = 0
    for s in shots:
        d = s.get("duration_seconds") or s.get("duration") or s.get("seconds")
        if d:
            expected += float(d)
            counted += 1

    if counted >= 3:
        lower = expected * 0.85
        upper = expected * 1.25
        if not (lower <= duration <= upper):
            fail(f"duration_outside_shotlist_window:{duration:.3f}:expected_sum_{expected:.3f}")

def frame_metrics(path: Path):
    frame_w, frame_h = 160, 90
    frame_size = frame_w * frame_h

    raw = subprocess.check_output([
        "ffmpeg", "-v", "error",
        "-i", str(path),
        "-vf", f"fps=1/2,scale={frame_w}:{frame_h}:flags=bilinear,format=gray",
        "-frames:v", "40",
        "-f", "rawvideo",
        "pipe:1",
    ], timeout=60)

    count = len(raw) // frame_size
    if count < 4:
        fail("too_few_sampled_frames")

    frames = [raw[i * frame_size:(i + 1) * frame_size] for i in range(count)]

    complexities = []
    for fr in frames:
        mean = sum(fr) / len(fr)
        var = sum((b - mean) * (b - mean) for b in fr) / len(fr)
        complexities.append(math.sqrt(var))

    motions = []
    for a, b in zip(frames, frames[1:]):
        motions.append(sum(abs(x - y) for x, y in zip(a, b)) / frame_size)

    return max(motions), sum(complexities) / len(complexities), count

try:
    motion, complexity, sampled = frame_metrics(FINAL)
except subprocess.TimeoutExpired:
    fail("frame_metric_timeout")
except Exception as e:
    fail(f"frame_metric_failed:{e}")

if motion < MIN_MOTION_SCORE:
    fail(f"final_motion_too_low:{motion:.3f}")

if complexity < MIN_COMPLEXITY_SCORE:
    fail(f"final_visual_complexity_too_low:{complexity:.3f}")

print("FINAL_FILM_MEDIA_QC_PASS=true")
print(f"FINAL={FINAL}")
print(f"WIDTH={width}")
print(f"HEIGHT={height}")
print(f"DURATION_SECONDS={duration:.3f}")
print(f"SIZE_BYTES={size}")
print(f"MOTION_SCORE={motion:.3f}")
print(f"COMPLEXITY_SCORE={complexity:.3f}")
print(f"SAMPLED_FRAMES={sampled}")
