#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/midiakiasat/Downloads/Apps/midiakiasat/Kaaffilm/CINEMATICUM"
COMFY="$ROOT/.runtime/ComfyUI"
LOG="$ROOT/.runtime/comfyui-8188.log"
PID="$ROOT/.runtime/comfyui-8188.pid"

if curl -fsS http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
  echo "COMFYUI_ALREADY_RUNNING=true"
  exit 0
fi

cd "$COMFY"
nohup "$COMFY/.venv/bin/python" main.py --listen 127.0.0.1 --port 8188 > "$LOG" 2>&1 &
echo $! > "$PID"

for i in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
    echo "COMFYUI_RUNNING=true"
    echo "COMFYUI_URL=http://127.0.0.1:8188"
    echo "COMFYUI_LOG=$LOG"
    exit 0
  fi
  sleep 2
done

echo "COMFYUI_START_FAIL=true"
echo "LOG=$LOG"
tail -80 "$LOG" || true
exit 1
