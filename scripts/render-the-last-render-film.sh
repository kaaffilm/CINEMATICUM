#!/usr/bin/env bash
set -euo pipefail

SRC="source/films/THE_LAST_RENDER/shots"
OUT="dist/films/THE_LAST_RENDER"
FINAL="$OUT/THE_LAST_RENDER.mp4"

mkdir -p "$OUT"

count="$(find "$SRC" -type f \( -name '*.mp4' -o -name '*.mov' -o -name '*.mkv' \) | wc -l | tr -d ' ')"

if [ "$count" -lt 3 ]; then
  echo "FILM_RENDER_REFUSED=true"
  echo "REASON=no_real_source_shots"
  echo "REQUIRED=place at least 3 real shot video files in $SRC"
  exit 1
fi

rm -f "$OUT/concat.txt"

find "$SRC" -type f \( -name '*.mp4' -o -name '*.mov' -o -name '*.mkv' \) | sort | while read -r f; do
  printf "file '%s'\n" "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")" >> "$OUT/concat.txt"
done

ffmpeg -y -f concat -safe 0 -i "$OUT/concat.txt" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium \
  -c:a aac -b:a 192k \
  "$FINAL"

ffprobe -v error -show_format -show_streams "$FINAL" > "$OUT/ffprobe.txt"

echo "REAL_FILM_RENDERED=true"
echo "OPEN_THIS=$FINAL"
