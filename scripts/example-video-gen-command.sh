#!/usr/bin/env bash
set -euo pipefail
cat >&2 <<EOF
This is only the adapter contract.

Your real backend command must read:
  SHOT_ID=$SHOT_ID
  PROMPT_FILE=$PROMPT_FILE
  OUT_MP4=$OUT_MP4
  DURATION=$DURATION
  WIDTH=$WIDTH
  HEIGHT=$HEIGHT
  FPS=$FPS

It must create:
  $OUT_MP4

Do not use this example as a renderer.
EOF
exit 64
