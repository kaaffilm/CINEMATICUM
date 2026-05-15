#!/usr/bin/env bash
set -euo pipefail

echo "BACKEND CONTRACT ONLY. This script does not generate fake footage." >&2
echo "Your real backend command must read:" >&2
echo "  SHOT_ID PROMPT_FILE OUT_MP4 DURATION WIDTH HEIGHT FPS" >&2
echo "and must write a real MP4 to OUT_MP4." >&2

exit 64
