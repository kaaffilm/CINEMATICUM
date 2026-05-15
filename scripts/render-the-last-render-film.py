#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path.cwd()
FILM = "THE_LAST_RENDER"
PROD = ROOT / "production" / FILM
SRC = ROOT / "source" / "films" / FILM / "shots"
DIST = ROOT / "dist" / "films" / FILM
NORM = DIST / "normalized_shots"
FINAL = DIST / f"{FILM}.mp4"
MANIFEST = DIST / f"{FILM}_manifest.json"

ffmpeg = shutil.which("ffmpeg")
ffprobe = shutil.which("ffprobe")

if not ffmpeg or not ffprobe:
    print("RENDER_FAIL=true")
    print("FFMPEG_AND_FFPROBE_REQUIRED=true")
    sys.exit(1)

shotlist = json.loads((PROD / "shots" / "shotlist.json").read_text())
shots = shotlist["shots"]
width = int(shotlist.get("width", 1920))
height = int(shotlist.get("height", 1080))
fps = int(shotlist.get("fps", 24))

SRC.mkdir(parents=True, exist_ok=True)
DIST.mkdir(parents=True, exist_ok=True)
NORM.mkdir(parents=True, exist_ok=True)

backend = os.environ.get("VIDEO_GEN_COMMAND", "").strip()
sources = []
missing = []

for shot in shots:
    filename = shot.get("filename", f"{shot['id']}.mp4")
    src = SRC / filename

    if not src.exists():
        if not backend:
            missing.append(filename)
            continue

        env = os.environ.copy()
        env["FILM"] = FILM
        env["SHOT_ID"] = shot["id"]
        env["PROMPT_FILE"] = str(PROD / "prompts" / f"{shot['id']}.json")
        env["OUT_MP4"] = str(src)
        env["DURATION"] = str(shot["duration"])
        env["WIDTH"] = str(width)
        env["HEIGHT"] = str(height)
        env["FPS"] = str(fps)

        src.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(backend, shell=True, check=True, env=env)

    sources.append((shot, src))

if missing:
    print("REALISTIC_SOURCE_REQUIRED=true")
    print("MISSING_SOURCE_SHOTS=" + ",".join(missing))
    print("PUT_MP4S_HERE=source/films/THE_LAST_RENDER/shots/")
    print("OR_SET_VIDEO_GEN_COMMAND=true")
    sys.exit(1)

normalized = []

for shot, src in sources:
    sid = shot["id"]
    duration = str(shot["duration"])
    out = NORM / f"{sid}.mp4"

    probe = json.loads(subprocess.check_output([
        ffprobe, "-v", "error",
        "-show_entries", "stream=codec_type",
        "-of", "json",
        str(src)
    ], text=True))

    has_audio = any(s.get("codec_type") == "audio" for s in probe.get("streams", []))

    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},setsar=1,format=yuv420p"
    )

    if has_audio:
        cmd = [
            ffmpeg, "-y",
            "-i", str(src),
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-filter:v", vf,
            "-filter:a", "aresample=48000,asetpts=PTS-STARTPTS",
            "-t", duration,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "14",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(out)
        ]
    else:
        cmd = [
            ffmpeg, "-y",
            "-i", str(src),
            "-f", "lavfi",
            "-t", duration,
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-filter:v", vf,
            "-t", duration,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "14",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(out)
        ]

    subprocess.run(cmd, check=True)
    normalized.append(out)
    print(f"NORMALIZED_SHOT={sid}")

concat = DIST / "concat.txt"
concat.write_text("".join(f"file '{p.resolve()}'\n" for p in normalized), encoding="utf-8")

assembled = DIST / f"{FILM}_assembled.mp4"

subprocess.run([
    ffmpeg, "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", str(concat),
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "14",
    "-c:a", "aac",
    "-b:a", "192k",
    "-movflags", "+faststart",
    str(assembled)
], check=True)

if FINAL.exists():
    FINAL.unlink()

assembled.rename(FINAL)

probe = json.loads(subprocess.check_output([
    ffprobe,
    "-v", "error",
    "-show_entries", "format=duration,size:stream=codec_type,width,height,codec_name",
    "-of", "json",
    str(FINAL)
], text=True))

sha = hashlib.sha256(FINAL.read_bytes()).hexdigest()

manifest = {
    "artifact": FILM,
    "artifact_class": "REALISTIC_SOURCE_SHOT_FILM",
    "toy_renderer_allowed": False,
    "fake_fallback_allowed": False,
    "path": str(FINAL),
    "sha256": sha,
    "duration_seconds": float(probe["format"]["duration"]),
    "size_bytes": int(probe["format"]["size"]),
    "width": width,
    "height": height,
    "fps": fps,
    "shot_count": len(shots),
    "shots": shots,
    "source_shots": [str(src) for _, src in sources]
}

MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

print("REALISTIC_FILM_RENDERED=true")
print(f"OPEN_THIS={FINAL}")
print(f"SHA256={sha}")
print(f"DURATION_SECONDS={manifest['duration_seconds']}")
