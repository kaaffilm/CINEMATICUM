#!/usr/bin/env bash
set -euo pipefail

W=854
H=480
FPS=24
OUT_DIR="dist/films/THE_LAST_RENDER"
SEG_DIR="$OUT_DIR/segments"
OUT_MP4="$OUT_DIR/THE_LAST_RENDER.mp4"
SHOT_LIST="$OUT_DIR/THE_LAST_RENDER.shots.json"
MANIFEST="$OUT_DIR/THE_LAST_RENDER.manifest.json"
CONCAT_LIST="$OUT_DIR/concat.txt"

rm -rf "$OUT_DIR"
mkdir -p "$SEG_DIR"

render_shot() {
  local name="$1"
  local dur="$2"
  local base="$3"
  local freq="$4"
  local vf="$5"
  local af="$6"
  local out="$SEG_DIR/${name}.mp4"

  echo "RENDER_SHOT=$name DUR=$dur"

  ffmpeg -y -hide_banner -loglevel error \
    -f lavfi -i "color=c=${base}:s=${W}x${H}:r=${FPS}:d=${dur}" \
    -f lavfi -i "sine=frequency=${freq}:sample_rate=48000:d=${dur}" \
    -map 0:v:0 -map 1:a:0 \
    -vf "${vf},format=yuv420p" \
    -af "${af},volume=0.22" \
    -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p \
    -c:a aac -b:a 192k -shortest "$out"
}

render_shot "001_title_threshold" 4.0 "black" 55 \
"drawbox=x=118:y=207:w=618:h=66:color=white@0.08:t=fill,drawbox=x=118:y=291:w=618:h=4:color=white@0.42:t=fill,drawbox=x=180:y=225:w=34:h=34:color=white@0.75:t=fill,drawbox=x=236:y=225:w=34:h=34:color=white@0.55:t=fill,drawbox=x=292:y=225:w=34:h=34:color=white@0.35:t=fill" \
"afade=t=in:st=0:d=1.0,afade=t=out:st=3.2:d=0.8"

render_shot "002_exterior_approach" 7.0 "midnightblue" 73 \
"drawbox=x=0:y=305:w=854:h=175:color=black@0.70:t=fill,drawbox=x=0:y=302:w=854:h=3:color=white@0.25:t=fill,drawbox=x=680:y=72:w=46:h=46:color=white@0.55:t=fill,drawbox=x='-80+92*t':y=252:w=30:h=76:color=white@0.78:t=fill,drawbox=x='-72+92*t':y=236:w=14:h=14:color=white@0.78:t=fill,drawbox=x='-95+92*t':y=330:w=88:h=7:color=black@0.55:t=fill" \
"aecho=0.8:0.8:900:0.25,afade=t=in:st=0:d=1.0,afade=t=out:st=6.2:d=0.8"

render_shot "003_door_refuses" 6.0 "black" 88 \
"drawbox=x=222:y=70:w=410:h=360:color=white@0.08:t=fill,drawbox=x=242:y=88:w=370:h=324:color=black@0.80:t=fill,drawbox=x=418:y=88:w=18:h=324:color=white@0.22:t=fill,drawbox=x='120+36*t':y=238:w=42:h=118:color=white@0.72:t=fill,drawbox=x='132+36*t':y=220:w=18:h=18:color=white@0.72:t=fill,drawbox=x=604:y=238:w=10:h=10:color=white@0.80:t=fill" \
"aecho=0.8:0.7:650:0.20"

render_shot "004_corridor_cut" 7.0 "black" 110 \
"drawbox=x=0:y=0:w=854:h=480:color=black:t=fill,drawbox=x=95:y=70:w=664:h=340:color=white@0.04:t=fill,drawbox=x=155:y=112:w=544:h=256:color=black@0.70:t=fill,drawbox=x=213:y=154:w=428:h=172:color=white@0.06:t=fill,drawbox=x=0:y=238:w=854:h=2:color=white@0.15:t=fill,drawbox=x='40+82*t':y=250:w=36:h=92:color=white@0.76:t=fill,drawbox=x='48+82*t':y=232:w=20:h=20:color=white@0.76:t=fill" \
"aecho=0.8:0.8:420:0.35"

render_shot "005_machine_room" 7.0 "darkslategray" 147 \
"drawgrid=width=64:height=64:thickness=1:color=white@0.14,drawbox=x=66:y=62:w=722:h=356:color=black@0.35:t=fill,drawbox=x=96:y=92:w=110:h=256:color=cyan@0.16:t=fill,drawbox=x=246:y=92:w=110:h=256:color=cyan@0.16:t=fill,drawbox=x=396:y=92:w=110:h=256:color=cyan@0.16:t=fill,drawbox=x=546:y=92:w=110:h=256:color=cyan@0.16:t=fill,drawbox=x='80+95*t':y=374:w=96:h=8:color=red@0.80:t=fill,drawbox=x=395:y=210:w=64:h=100:color=white@0.68:t=fill" \
"acompressor=threshold=-18dB:ratio=5:attack=20:release=200"

render_shot "006_hand_on_switch" 5.0 "black" 196 \
"drawbox=x=172:y=116:w=510:h=248:color=white@0.08:t=fill,drawbox=x=232:y=164:w=390:h=112:color=black@0.70:t=fill,drawbox=x=284:y=196:w=48:h=48:color=red@0.75:t=fill,drawbox=x=352:y=196:w=48:h=48:color=white@0.22:t=fill,drawbox=x=420:y=196:w=48:h=48:color=white@0.22:t=fill,drawbox=x='-180+116*t':y=260:w=260:h=54:color=white@0.62:t=fill,drawbox=x='28+116*t':y=246:w=44:h=44:color=white@0.72:t=fill" \
"aecho=0.8:0.9:280:0.45"

render_shot "007_breaking_pattern" 6.0 "maroon" 233 \
"drawbox=x=0:y=0:w=854:h=480:color=black@0.22:t=fill,drawbox=x=48:y=44:w=758:h=392:color=white@0.05:t=fill,drawbox=x=84:y=80:w=96:h=320:color=white@0.34:t=fill,drawbox=x=222:y=54:w=34:h=370:color=black@0.80:t=fill,drawbox=x=318:y=80:w=130:h=320:color=white@0.28:t=fill,drawbox=x=492:y=54:w=34:h=370:color=black@0.80:t=fill,drawbox=x=594:y=80:w=176:h=320:color=white@0.20:t=fill,drawbox=x='720-96*t':y=118:w=42:h=250:color=red@0.90:t=fill" \
"acrusher=level_in=0.8:level_out=0.7:bits=10:mode=log"

render_shot "008_silence_after_cut" 5.0 "black" 41 \
"drawbox=x=0:y=0:w=854:h=480:color=black:t=fill,drawbox=x='420+4*t':y='236-2*t':w=14:h=14:color=white@0.62:t=fill,drawbox=x=0:y=416:w=854:h=2:color=white@0.06:t=fill" \
"volume=0.08,afade=t=in:st=0:d=1.8,afade=t=out:st=3.5:d=1.5"

render_shot "009_exit_release" 8.0 "midnightblue" 82 \
"drawbox=x=0:y=310:w=854:h=170:color=black@0.74:t=fill,drawbox=x=0:y=308:w=854:h=3:color=white@0.28:t=fill,drawbox=x=330:y=92:w=194:h=218:color=white@0.10:t=fill,drawbox=x=364:y=124:w=126:h=186:color=black@0.72:t=fill,drawbox=x='380+42*t':y=246:w=34:h=84:color=white@0.74:t=fill,drawbox=x='389+42*t':y=228:w=18:h=18:color=white@0.74:t=fill,drawbox=x='345+28*t':y=88:w=164:h=4:color=white@0.48:t=fill" \
"aecho=0.8:0.9:1000:0.28,afade=t=out:st=7.0:d=1.0"

render_shot "010_end_lock" 4.0 "black" 55 \
"drawbox=x=118:y=230:w=618:h=4:color=white@0.50:t=fill,drawbox=x=410:y=204:w=34:h=34:color=white@0.75:t=fill,drawbox=x=410:y=260:w=34:h=34:color=white@0.25:t=fill" \
"afade=t=out:st=2.4:d=1.6"

cat > "$SHOT_LIST" <<JSON
{
  "title": "THE_LAST_RENDER",
  "artifact_class": "SHOT_BASED_SHORT_FILM",
  "not_a_smoke_test": true,
  "not_a_manifest_proof": true,
  "fps": $FPS,
  "width": $W,
  "height": $H,
  "shots": [
    {"id":"001_title_threshold","duration_seconds":4.0,"function":"opens the threshold"},
    {"id":"002_exterior_approach","duration_seconds":7.0,"function":"establishes figure and approach"},
    {"id":"003_door_refuses","duration_seconds":6.0,"function":"first obstacle"},
    {"id":"004_corridor_cut","duration_seconds":7.0,"function":"interior movement through cut space"},
    {"id":"005_machine_room","duration_seconds":7.0,"function":"confronts the rendering machine"},
    {"id":"006_hand_on_switch","duration_seconds":5.0,"function":"human action changes state"},
    {"id":"007_breaking_pattern","duration_seconds":6.0,"function":"rupture montage"},
    {"id":"008_silence_after_cut","duration_seconds":5.0,"function":"negative space after rupture"},
    {"id":"009_exit_release","duration_seconds":8.0,"function":"release and exit"},
    {"id":"010_end_lock","duration_seconds":4.0,"function":"closure image"}
  ]
}
JSON

: > "$CONCAT_LIST"
for f in "$SEG_DIR"/*.mp4; do
  printf "file '%s'\n" "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")" >> "$CONCAT_LIST"
done

ffmpeg -y -hide_banner -loglevel error \
  -f concat -safe 0 -i "$CONCAT_LIST" \
  -c copy "$OUT_MP4"

python3 - <<PY
import json, hashlib, subprocess
from pathlib import Path

out = Path("$OUT_MP4")
shot_list = Path("$SHOT_LIST")
manifest = Path("$MANIFEST")
seg_dir = Path("$SEG_DIR")

if not out.exists():
    raise SystemExit("FINAL_MP4_MISSING")

probe = json.loads(subprocess.check_output([
    "ffprobe", "-v", "error",
    "-print_format", "json",
    "-show_format", "-show_streams",
    str(out)
], text=True))

video = next(s for s in probe["streams"] if s["codec_type"] == "video")
audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
duration = float(probe["format"]["duration"])
size = int(probe["format"]["size"])

sha = hashlib.sha256(out.read_bytes()).hexdigest()
shots = json.loads(shot_list.read_text())["shots"]
segments = sorted(seg_dir.glob("*.mp4"))

assert len(shots) == 10, len(shots)
assert len(segments) == 10, len(segments)
assert duration >= 58.0, duration
assert size > 1_000_000, size
assert int(video["width"]) == 854
assert int(video["height"]) == 480
assert video["codec_name"] == "h264"
assert audio["codec_name"] == "aac"

manifest.write_text(json.dumps({
    "artifact": "THE_LAST_RENDER",
    "artifact_class": "SHOT_BASED_SHORT_FILM",
    "not_smoke_test": True,
    "not_single_fractal_loop": True,
    "not_manifest_proof": True,
    "path": str(out),
    "sha256": sha,
    "size_bytes": size,
    "duration_seconds": duration,
    "width": int(video["width"]),
    "height": int(video["height"]),
    "video_codec": video["codec_name"],
    "audio_codec": audio["codec_name"],
    "shot_count": len(shots),
    "cut_count_minimum": len(shots) - 1,
    "shots": shots
}, indent=2) + "\\n")

print(f"THE_LAST_RENDER_MP4={out}")
print(f"THE_LAST_RENDER_SHA256={sha}")
print(f"DURATION_SECONDS={duration:.3f}")
print(f"SIZE_BYTES={size}")
print("SHOT_BASED_FILM_RENDER_PASS=true")
PY
