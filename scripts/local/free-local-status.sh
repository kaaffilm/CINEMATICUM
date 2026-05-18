#!/usr/bin/env bash
set -euo pipefail
ROOT="/Users/midiakiasat/Downloads/Apps/midiakiasat/Kaaffilm/CINEMATICUM"
COMFY="$ROOT/.runtime/ComfyUI"

echo "COMFYUI_RUNNING=$(curl -fsS http://127.0.0.1:8188/system_stats >/dev/null 2>&1 && echo true || echo false)"
echo "WAN_DIFFUSION_PRESENT=$(test -s "$COMFY/models/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors" && echo true || echo false)"
echo "WAN_TEXT_ENCODER_PRESENT=$(test -s "$COMFY/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" && echo true || echo false)"
echo "WAN_VAE_PRESENT=$(test -s "$COMFY/models/vae/wan_2.1_vae.safetensors" && echo true || echo false)"
echo "API_WORKFLOW_PRESENT=$(test -s "$ROOT/production/THE_LAST_RENDER/workflows/comfyui-api.json" && echo true || echo false)"
