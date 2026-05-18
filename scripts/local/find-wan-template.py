import json
from pathlib import Path
import sys

root = Path("/Users/midiakiasat/Downloads/Apps/midiakiasat/Kaaffilm/CINEMATICUM")
comfy = root / ".runtime/ComfyUI"
out = root / "production/THE_LAST_RENDER/workflows/comfyui-api.json"

candidates = []
for base in [
    comfy,
    comfy / ".venv/lib/python3.14/site-packages",
    comfy / "user",
]:
    if base.exists():
        candidates += list(base.rglob("*.json"))

needles = ["wan2.1", "Wan", "t2v", "1.3B"]
for p in candidates:
    try:
        s = p.read_text(errors="ignore")
    except Exception:
        continue
    low = s.lower()
    if "wan" in low and ("t2v" in low or "text" in low) and ("1.3" in low or "13b" in low or "1.3b" in low):
        try:
            data = json.loads(s)
        except Exception:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"WAN_TEMPLATE_FOUND={p}")
        print(f"WORKFLOW_WRITTEN={out}")
        print("FREE_LOCAL_WORKFLOW_READY=true")
        sys.exit(0)

print("WAN_TEMPLATE_NOT_FOUND=true")
print("MANUAL_STEP=ComfyUI -> Browse Templates -> Video -> Wan2.1 Text to Video -> load -> File -> Export API")
print(f"SAVE_EXACTLY={out}")
sys.exit(1)
