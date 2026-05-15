#!/usr/bin/env python3
from pathlib import Path
import json
import sys

ROOT = Path.cwd()
FILM = "THE_LAST_RENDER"

required = [
    "production/THE_LAST_RENDER/shots/shotlist.json",
    "production/THE_LAST_RENDER/story/TREATMENT.md",
    "production/THE_LAST_RENDER/story/SCREENPLAY.md",
    "production/THE_LAST_RENDER/contracts/REALISTIC_FILM_STACK_CONTRACT.md",
    "production/THE_LAST_RENDER/camera/CAMERA_PLAN.md",
    "production/THE_LAST_RENDER/color/look.json",
    "production/THE_LAST_RENDER/sound/sound_design_plan.json",
    "scripts/qc-no-toy-stack.py",
    "scripts/qc-source-shots.py",
    "scripts/qc-final-film.py",
    "scripts/render-the-last-render-film.py",
    "scripts/render-the-last-render-film.sh",
    "Makefile"
]

missing = [p for p in required if not (ROOT / p).exists()]
if missing:
    print("NO_TOY_STACK_QC_FAIL=true")
    print("MISSING=" + ",".join(missing))
    sys.exit(1)

forbidden_paths = [
    "scripts/generate-the-last-render-source-shots.py",
    "scripts/render-real-film.sh",
    "source/films/THE_LAST_RENDER/generated_stills"
]

present = [p for p in forbidden_paths if (ROOT / p).exists()]
if present:
    print("NO_TOY_STACK_QC_FAIL=true")
    print("FORBIDDEN_TOY_PATH_PRESENT=" + ",".join(present))
    sys.exit(1)

shotlist = json.loads((ROOT / "production/THE_LAST_RENDER/shots/shotlist.json").read_text())
shots = shotlist.get("shots", [])

if shotlist.get("toy_renderer_allowed") is not False:
    print("NO_TOY_STACK_QC_FAIL=true")
    print("toy_renderer_allowed must be false")
    sys.exit(1)

if shotlist.get("fake_fallback_allowed") is not False:
    print("NO_TOY_STACK_QC_FAIL=true")
    print("fake_fallback_allowed must be false")
    sys.exit(1)

if len(shots) < 16:
    print("NO_TOY_STACK_QC_FAIL=true")
    print(f"SHOT_COUNT_TOO_LOW={len(shots)}")
    sys.exit(1)

ids = [s.get("id") for s in shots]
if len(ids) != len(set(ids)):
    print("NO_TOY_STACK_QC_FAIL=true")
    print("DUPLICATE_SHOT_IDS=true")
    sys.exit(1)

missing_prompts = []
for shot in shots:
    sid = shot["id"]
    prompt = ROOT / "production/THE_LAST_RENDER/prompts" / f"{sid}.json"
    if not prompt.exists():
        missing_prompts.append(sid)

if missing_prompts:
    print("NO_TOY_STACK_QC_FAIL=true")
    print("MISSING_PROMPTS=" + ",".join(missing_prompts))
    sys.exit(1)

print("NO_TOY_STACK_QC_PASS=true")
print(f"SHOT_COUNT={len(shots)}")
print("REALISTIC_STACK_CONTRACT=true")
