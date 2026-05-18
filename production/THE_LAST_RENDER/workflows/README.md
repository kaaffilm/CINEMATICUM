# CINEMATICUM Native Local Video Backend

No fal.ai.

Required workflow file:

    production/THE_LAST_RENDER/workflows/comfyui-api.json

This must be a ComfyUI **API-format** workflow that outputs video.

Supported placeholders inside the workflow JSON:

    {{PROMPT}}
    {{NEGATIVE_PROMPT}}
    {{SEED}}
    {{WIDTH}}
    {{HEIGHT}}
    {{FRAMES}}
    {{FPS}}
    {{OUTPUT_PREFIX}}

Run local ComfyUI on:

    http://127.0.0.1:8188
