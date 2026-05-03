#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RECEIPT_PATH="${RECEIPT_PATH:-${TMPDIR:-/tmp}/CINEMATICUM_CINEMATIC_JURISDICTION_RECEIPT.json}"

python3 - "$RECEIPT_PATH" <<'PY'
import json
import sys
from pathlib import Path

root = Path(".")
receipt_path = Path(sys.argv[1])

required_files = [
    "CHARTER_OF_CINEMATIC_JURISDICTION.json",
    "ADMISSIBLE_MOTION_PICTURE_STANDARD.json",
    "DIRECTORIAL_AUTHORITY_LAW.json",
    "FINAL_CUT_JURISDICTION.json",
    "TIMELINE_EVIDENCE_LAW.json",
    "RELEASE_ADMISSIBILITY_LAW.json",
    "LOCAL_SOVEREIGN_PRODUCTION_LAW.json",
    "FORBIDDEN_REDUCTIONS.json",
    "MOTION_PICTURE_ISSUANCE_ACT.json",
    "CASES/CASE_001_THE_LAST_RENDER/CASE_CHARTER.json",
    "CASES/CASE_001_THE_LAST_RENDER/FINAL_CUT_LAW.json",
    "CASES/CASE_001_THE_LAST_RENDER/ADMISSIBILITY_TARGET.json",
]

for rel in required_files:
    if not (root / rel).is_file():
        raise SystemExit(f"missing required file: {rel}")

charter = json.loads((root / "CHARTER_OF_CINEMATIC_JURISDICTION.json").read_text())
case = json.loads((root / "CASES/CASE_001_THE_LAST_RENDER/CASE_CHARTER.json").read_text())
local = json.loads((root / "LOCAL_SOVEREIGN_PRODUCTION_LAW.json").read_text())
standard = json.loads((root / "ADMISSIBLE_MOTION_PICTURE_STANDARD.json").read_text())

def eq(actual, expected, key):
    if actual != expected:
        raise SystemExit(f"{key}: {actual!r} != {expected!r}")

eq(charter["root_sentence"], "CINEMATICUM issues admissible motion pictures.", "root_sentence")
eq(charter["institution"], "CINEMATICUM", "institution")
eq(charter["repo"], "kaaffilm/CINEMATICUM", "repo")
eq(charter["primary_form"], "sovereign_cinematic_jurisdiction", "primary_form")
eq(charter["issued_object"], "admissible_motion_picture", "issued_object")
eq(charter["first_case"], "CASE_001_THE_LAST_RENDER", "first_case")
eq(charter["first_case_title"], "THE LAST RENDER", "first_case_title")
eq(charter["local_only"], True, "local_only")
eq(charter["paid_api_allowed"], False, "paid_api_allowed")
eq(charter["cloud_render_allowed"], False, "cloud_render_allowed")
eq(charter["raw_media_in_git"], False, "raw_media_in_git")
eq(charter["model_weights_in_git"], False, "model_weights_in_git")
eq(charter["pass_condition"], "CINEMATICUM_CINEMATIC_JURISDICTION_PASS", "pass_condition")

for forbidden in [
    "ai_video_generator",
    "prompt_pipeline",
    "model_showcase",
    "demo_clip",
    "tech_preview",
    "automation_wrapper",
    "asset_factory",
    "render_farm",
    "workflow_collection",
]:
    if forbidden not in charter["forbidden_reductions"]:
        raise SystemExit(f"missing forbidden reduction: {forbidden}")

eq(case["case_id"], "CASE_001_THE_LAST_RENDER", "case_id")
eq(case["title"], "THE LAST RENDER", "case title")
eq(case["not_demo"], True, "not_demo")
eq(case["not_experiment"], True, "not_experiment")
eq(case["not_ai_film_label"], True, "not_ai_film_label")

eq(local["local_only"], True, "local law local_only")
eq(local["paid_api_allowed"], False, "local law paid_api_allowed")
eq(local["cloud_render_allowed"], False, "local law cloud_render_allowed")
eq(local["model_weights_in_git"], False, "local law model_weights_in_git")
eq(local["raw_media_in_git"], False, "local law raw_media_in_git")

eq(standard["object_type"], "admissible_motion_picture", "standard object_type")

for forbidden_path in ["engine", "models.lock", "workflows", "models", "renders", "frames", "exports"]:
    if (root / forbidden_path).exists():
        raise SystemExit(f"PR1 forbidden path exists: {forbidden_path}")

gitignore = (root / ".gitignore").read_text()
for pattern in ["*.mp4", "*.mov", "*.wav", "*.safetensors", "*.ckpt", "/models/", "/renders/", "/frames/"]:
    if pattern not in gitignore:
        raise SystemExit(f"missing gitignore boundary pattern: {pattern}")

receipt = {
    "pass": True,
    "jurisdiction": "CINEMATICUM",
    "root_sentence": "CINEMATICUM issues admissible motion pictures.",
    "issued_object": "ADMISSIBLE_MOTION_PICTURE",
    "case_001": "THE_LAST_RENDER",
    "local_only": True,
    "paid_api": False,
    "cloud_render": False,
    "raw_media_in_git": False,
    "model_weights_in_git": False,
    "pass_condition": "CINEMATICUM_CINEMATIC_JURISDICTION_PASS"
}
receipt_path.parent.mkdir(parents=True, exist_ok=True)
receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

print("CINEMATICUM CINEMATIC JURISDICTION: PASS")
print('ROOT_SENTENCE="CINEMATICUM issues admissible motion pictures."')
print("JURISDICTION=CINEMATICUM")
print("ISSUED_OBJECT=ADMISSIBLE_MOTION_PICTURE")
print("CASE_001=THE_LAST_RENDER")
print("NOT_AI_VIDEO_GENERATOR=true")
print("NOT_PROMPT_PIPELINE=true")
print("NOT_MODEL_SHOWCASE=true")
print("NOT_DEMO_CLIP=true")
print("DIRECTOR_AUTHORITY_REQUIRED=true")
print("FINAL_CUT_JURISDICTION_REQUIRED=true")
print("TIMELINE_EVIDENCE_REQUIRED=true")
print("RELEASE_ADMISSIBILITY_REQUIRED=true")
print("AUDIENCE_ARTIFACT_REQUIRED=true")
print("PROOF_ARTIFACT_REQUIRED=true")
print("OUTSIDER_REPLAY_REQUIRED=true")
print("TERMINAL_CLOSURE_REQUIRED=true")
print("LOCAL_ONLY=true")
print("PAID_API=false")
print("CLOUD_RENDER=false")
print("RAW_MEDIA_IN_GIT=false")
print("MODEL_WEIGHTS_IN_GIT=false")
PY
