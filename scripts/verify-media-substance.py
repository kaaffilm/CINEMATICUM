#!/usr/bin/env python3
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
RECORD = ROOT / "records/motion_picture_issuance/MOTION_PICTURE_MEDIA_ADMISSION_RECORD.json"

MIN_DURATION_SECONDS = 30
MIN_WIDTH = 640
MIN_HEIGHT = 360
MIN_SAMPLE_FRAMES = 8
MIN_SPATIAL_STD = 12.0
MIN_PASSING_STD_FRAMES = 4
MIN_EDGE_DENSITY = 0.008

def fail(reason):
    print("MEDIA_SUBSTANCE_PASS=false")
    print(f"REASON={reason}")
    raise SystemExit(1)

def load_record():
    if not RECORD.exists():
        fail(f"missing_record={RECORD}")
    return json.loads(RECORD.read_text())

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def candidate_paths(record):
    paths = []

    env_file = os.environ.get("CINEMATICUM_MEDIA_FILE")
    if env_file:
        paths.append(Path(env_file).expanduser())

    uri = str(record.get("media_uri", ""))
    name = record.get("media_name") or Path(uri).name

    qroot = os.environ.get("CINEMATICUM_MEDIA_QUARANTINE")
    if qroot and uri.startswith("local-quarantine://"):
        rel = uri.removeprefix("local-quarantine://")
        paths.append(Path(qroot).expanduser() / rel)

    local_candidates = [
        ROOT / ".cinematicum_media",
        ROOT.parent / "CINEMATICUM_LOCAL_MEDIA_QUARANTINE",
        Path.home() / "Downloads/Apps/midiakiasat/Kaaffilm/CINEMATICUM_LOCAL_MEDIA_QUARANTINE",
    ]

    for base in local_candidates:
        if base.exists() and name:
            paths.extend(base.rglob(name))

    return paths

def locate_media(record):
    for p in candidate_paths(record):
        if p.exists() and p.is_file():
            return p
    fail("media_file_not_found_set_CINEMATICUM_MEDIA_FILE=/absolute/path/to/real_final_media.mp4")

def ffprobe(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,nb_frames,r_frame_rate:format=duration,size",
        "-of", "json",
        str(path),
    ]
    try:
        data = subprocess.check_output(cmd, text=True)
    except FileNotFoundError:
        fail("ffprobe_not_found_install_ffmpeg")
    except subprocess.CalledProcessError as e:
        fail(f"ffprobe_failed={e}")
    return json.loads(data)

def sample_gray_frames(path, width=160, height=90):
    frame_size = width * height
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", str(path),
        "-vf", f"fps=1/5,scale={width}:{height},format=gray",
        "-f", "rawvideo",
        "-",
    ]
    try:
        raw = subprocess.check_output(cmd)
    except FileNotFoundError:
        fail("ffmpeg_not_found_install_ffmpeg")
    except subprocess.CalledProcessError as e:
        fail(f"ffmpeg_sample_failed={e}")

    frames = []
    for i in range(0, len(raw), frame_size):
        chunk = raw[i:i + frame_size]
        if len(chunk) == frame_size:
            frames.append(chunk)
    return frames, width, height

def frame_std(frame):
    vals = list(frame)
    return statistics.pstdev(vals)

def edge_density(frame, width, height):
    hits = 0
    total = 0
    for y in range(height):
        row = y * width
        for x in range(width - 1):
            total += 1
            if abs(frame[row + x] - frame[row + x + 1]) > 10:
                hits += 1
    for y in range(height - 1):
        row = y * width
        next_row = (y + 1) * width
        for x in range(width):
            total += 1
            if abs(frame[row + x] - frame[next_row + x]) > 10:
                hits += 1
    return hits / max(1, total)

record = load_record()
media = locate_media(record)

expected_sha = record.get("media_sha256")
if expected_sha and sha256(media) != expected_sha:
    fail("media_sha256_mismatch")

expected_bytes = record.get("media_bytes")
if expected_bytes and media.stat().st_size != int(expected_bytes):
    fail("media_size_mismatch")

probe = ffprobe(media)
fmt = probe.get("format", {})
streams = probe.get("streams", [])
if not streams:
    fail("no_video_stream")

stream = streams[0]
duration = float(fmt.get("duration") or 0)
width = int(stream.get("width") or 0)
height = int(stream.get("height") or 0)

if duration < MIN_DURATION_SECONDS:
    fail(f"duration_too_short={duration}")

if width < MIN_WIDTH or height < MIN_HEIGHT:
    fail(f"resolution_too_low={width}x{height}")

frames, sw, sh = sample_gray_frames(media)
if len(frames) < MIN_SAMPLE_FRAMES:
    fail(f"not_enough_sample_frames={len(frames)}")

stds = [frame_std(f) for f in frames]
edges = [edge_density(f, sw, sh) for f in frames]

passing_std = sum(1 for s in stds if s >= MIN_SPATIAL_STD)
mean_edge = sum(edges) / len(edges)

if passing_std < MIN_PASSING_STD_FRAMES:
    fail(f"flat_or_card_sequence=true passing_std_frames={passing_std} max_std={max(stds):.3f}")

if mean_edge < MIN_EDGE_DENSITY:
    fail(f"insufficient_visual_structure=true mean_edge_density={mean_edge:.6f}")

print("MEDIA_SUBSTANCE_PASS=true")
print(f"MEDIA_FILE={media}")
print(f"DURATION_SECONDS={duration:.3f}")
print(f"RESOLUTION={width}x{height}")
print(f"SAMPLED_FRAMES={len(frames)}")
print(f"PASSING_STD_FRAMES={passing_std}")
print(f"MEAN_EDGE_DENSITY={mean_edge:.6f}")
