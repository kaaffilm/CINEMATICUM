#!/usr/bin/env bash
set -euo pipefail

DURATION="${DURATION:-36}"
FPS="${FPS:-24}"
WIDTH="${WIDTH:-854}"
HEIGHT="${HEIGHT:-480}"
OUT="${OUT:-dist/films/THE_LAST_RENDER/THE_LAST_RENDER.mp4}"
MANIFEST="${OUT%.mp4}.manifest.json"

mkdir -p "$(dirname "$OUT")"

echo "REAL_FILM_RENDER_START=true"

ffmpeg -y \
  -f lavfi -t "$DURATION" \
  -i "mandelbrot=s=${WIDTH}x${HEIGHT}:rate=${FPS}:start_x=-0.7436438870371587:start_y=0.131825904205312:start_scale=2.8:end_scale=0.00008" \
  -f lavfi -t "$DURATION" \
  -i "sine=frequency=55:sample_rate=48000" \
  -filter_complex "[0:v]eq=contrast=1.35:saturation=1.25:brightness=-0.03,drawbox=y=0:h=36:color=black:t=fill,drawbox=y=$(($HEIGHT-36)):h=36:color=black:t=fill[vout];[1:a]aecho=0.8:0.88:900:0.28,volume=0.35[aout]" \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  "$OUT"

test -s "$OUT" || { echo "REAL_MP4_NOT_CREATED"; exit 1; }

SHA="$(shasum -a 256 "$OUT" | awk '{print $1}')"
SIZE="$(stat -f%z "$OUT" 2>/dev/null || stat -c%s "$OUT")"

cat > "$MANIFEST" <<EOF
{
  "artifact": "REAL_PLAYABLE_MP4",
  "path": "$OUT",
  "sha256": "$SHA",
  "size_bytes": $SIZE,
  "duration_seconds": $DURATION,
  "fps": $FPS,
  "width": $WIDTH,
  "height": $HEIGHT,
  "fake_proof": false,
  "proof_sprawl": false
}
EOF

ffprobe -v error -show_entries format=duration,size -of default=nw=1 "$OUT"

echo "REAL_FILM_MP4=$OUT"
echo "REAL_FILM_SHA256=$SHA"
echo "CINEMATICUM_REAL_FILM_RENDER_PASS=true"
