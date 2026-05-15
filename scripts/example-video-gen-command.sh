#!/usr/bin/env bash
set -euo pipefail
cat >&2 <<EOF
ADAPTER CONTRACT ONLY.

A real backend command must read:
  SHOT_ID=$SHOT_ID
  PROMPT_FILE=$PROMPT_FILE
  OUT_MP4=$OUT_MP4
  DURATION=$DURATION
  WIDTH=$WIDTH
  HEIGHT=$HEIGHT
  FPS=$FPS

It must create:
  $OUT_MP4
EOF
exit 64
