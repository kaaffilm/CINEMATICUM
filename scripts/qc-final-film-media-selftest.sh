#!/usr/bin/env bash
set -euo pipefail

FILM="THE_LAST_RENDER"
OUT_DIR="dist/films/$FILM"
FINAL="$OUT_DIR/$FILM.mp4"
TMP_BACKUP="$(mktemp -d)"

cleanup() {
  rm -rf "$OUT_DIR"
  if [ -d "$TMP_BACKUP/$FILM" ]; then
    mkdir -p dist/films
    mv "$TMP_BACKUP/$FILM" "$OUT_DIR"
  fi
  rm -rf "$TMP_BACKUP"
}
trap cleanup EXIT

if [ -d "$OUT_DIR" ]; then
  mkdir -p "$TMP_BACKUP"
  mv "$OUT_DIR" "$TMP_BACKUP/$FILM"
fi

mkdir -p "$OUT_DIR"

DUR="$(python3 - <<'PY'
import json
from pathlib import Path

p = Path("production/THE_LAST_RENDER/shots/shotlist.json")
data = json.loads(p.read_text())
shots = data.get("shots", data)

total = 0.0
for s in shots:
    total += float(s.get("duration_seconds") or s.get("duration") or s.get("seconds") or 0)

print(max(total, 46.0))
PY
)"

echo "GENERATE_BAD_STATIC_FINAL=true"
echo "DURATION_SECONDS=$DUR"

ffmpeg -v error -y \
  -f lavfi -i "color=c=black:s=1280x720:r=24:d=${DUR}" \
  -f lavfi -i "anullsrc=channel_layout=mono:sample_rate=48000" \
  -t "$DUR" \
  -c:v libx264 -pix_fmt yuv420p \
  -b:v 2500k -maxrate 2500k -bufsize 5000k \
  -x264-params "nal-hrd=cbr:force-cfr=1" \
  -c:a aac -b:a 128k \
  -movflags +faststart \
  "$FINAL"

set +e
python3 scripts/qc-final-film-media.py > "$OUT_DIR/final-media-selftest.out" 2>&1
code="$?"
set -e

cat "$OUT_DIR/final-media-selftest.out"

if [ "$code" -eq 0 ]; then
  echo "FINAL_FILM_MEDIA_SELFTEST_FAIL=true"
  echo "REASON=bad_static_final_passed_forensics"
  exit 1
fi

grep -q "FINAL_FILM_MEDIA_QC_FAIL=true" "$OUT_DIR/final-media-selftest.out" || {
  echo "FINAL_FILM_MEDIA_SELFTEST_FAIL=true"
  echo "REASON=qc_failed_without_expected_failure_marker"
  exit 1
}

echo "FINAL_FILM_MEDIA_SELFTEST_PASS=true"
