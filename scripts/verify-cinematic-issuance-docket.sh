#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RECEIPT_PATH="${RECEIPT_PATH:-${TMPDIR:-/tmp}/CINEMATICUM_ISSUANCE_DOCKET_RECEIPT.json}"

python3 - "$RECEIPT_PATH" <<'PY'
import json
import sys
from pathlib import Path

root = Path(".")
receipt_path = Path(sys.argv[1])

def load(rel):
    p = root / rel
    if not p.is_file():
        raise SystemExit(f"missing required file: {rel}")
    return json.loads(p.read_text())

charter = load("CHARTER_OF_CINEMATIC_JURISDICTION.json")
docket = load("ISSUANCE_DOCKET.json")
anatomy = load("ADMISSIBLE_FILM_OBJECT_ANATOMY.json")
ledger = load("DEPARTMENT_AUTHORITY_LEDGER.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CASE_DOCKET.json")
evidence = load("CASES/CASE_001_THE_LAST_RENDER/CASE_EVIDENCE_LEDGER.json")

def eq(a, b, k):
    if a != b:
        raise SystemExit(f"{k}: {a!r} != {b!r}")

eq(charter["root_sentence"], "CINEMATICUM issues admissible motion pictures.", "root_sentence")
eq(docket["institution"], "CINEMATICUM", "institution")
eq(docket["issued_object"], "admissible_motion_picture", "issued_object")
eq(docket["issuance_is_not_export"], True, "issuance_is_not_export")
eq(docket["issuance_is_not_generation"], True, "issuance_is_not_generation")
eq(docket["local_only"], True, "local_only")
eq(docket["paid_api_allowed"], False, "paid_api_allowed")
eq(docket["cloud_render_allowed"], False, "cloud_render_allowed")
eq(docket["raw_media_in_git"], False, "raw_media_in_git")
eq(docket["model_weights_in_git"], False, "model_weights_in_git")
eq(docket["pass_condition"], "CINEMATICUM_ISSUANCE_DOCKET_PASS", "pass_condition")

for required in [
    "audience_wound",
    "film_thesis",
    "director_authority",
    "shot_function_chain",
    "timeline_authority",
    "final_cut_lock",
    "public_release_object",
    "outsider_replay",
    "terminal_closure",
]:
    if required not in docket["issuance_requires"]:
        raise SystemExit(f"missing issuance requirement: {required}")

for body in ["audience_body", "evidentiary_body", "jurisdictional_body"]:
    if body not in anatomy["three_bodies"]:
        raise SystemExit(f"missing film body: {body}")

eq(anatomy["film_is_inadmissible_if_any_body_missing"], True, "film body completeness")
eq(ledger["department_status"], "decision_authorities_not_scripts", "department_status")
eq(ledger["model_output_status"], "raw_material_only", "model_output_status")

departments = {d["department"] for d in ledger["departments"]}
for required_department in ["director", "cinematographer", "editor", "sound", "release_archivist"]:
    if required_department not in departments:
        raise SystemExit(f"missing department: {required_department}")

eq(case["case_id"], "CASE_001_THE_LAST_RENDER", "case_id")
eq(case["docket_number"], "CIN-0001", "docket_number")
eq(case["title"], "THE LAST RENDER", "title")
eq(case["case_status"], "registered_under_jurisdiction", "case_status")
eq(case["not_demo"], True, "not_demo")
eq(case["not_model_showcase"], True, "not_model_showcase")
eq(case["not_prompt_pipeline"], True, "not_prompt_pipeline")

eq(evidence["media_admitted"], False, "media_admitted")
eq(evidence["generation_admitted"], False, "generation_admitted")
eq(evidence["engine_admitted"], False, "engine_admitted")

for forbidden_path in ["engine", "models.lock", "workflows", "models", "renders", "frames", "exports"]:
    if (root / forbidden_path).exists():
        raise SystemExit(f"PR2 forbidden path exists: {forbidden_path}")

tracked = []
try:
    import subprocess
    out = subprocess.check_output(["git", "ls-files"], text=True)
    tracked = [line.strip() for line in out.splitlines() if line.strip()]
except Exception:
    tracked = []

for path in tracked:
    if "__pycache__/" in path or path.endswith((".pyc", ".pyo")):
        raise SystemExit(f"source purity violation: {path}")
    if path.endswith((".mp4", ".mov", ".mkv", ".webm", ".wav", ".flac", ".safetensors", ".ckpt", ".pth", ".gguf")):
        raise SystemExit(f"heavy media/model violation: {path}")

receipt = {
    "pass": True,
    "jurisdiction": "CINEMATICUM",
    "docket": "motion_picture_issuance",
    "case_id": "CASE_001_THE_LAST_RENDER",
    "docket_number": "CIN-0001",
    "issued_object": "ADMISSIBLE_MOTION_PICTURE",
    "media_admitted": False,
    "generation_admitted": False,
    "engine_admitted": False,
    "pass_condition": "CINEMATICUM_ISSUANCE_DOCKET_PASS"
}
receipt_path.parent.mkdir(parents=True, exist_ok=True)
receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

print("CINEMATICUM ISSUANCE DOCKET: PASS")
print("JURISDICTION=CINEMATICUM")
print("DOCKET=MOTION_PICTURE_ISSUANCE")
print("CASE_001=THE_LAST_RENDER")
print("DOCKET_NUMBER=CIN-0001")
print("ISSUANCE_IS_NOT_GENERATION=true")
print("ISSUANCE_IS_NOT_EXPORT=true")
print("DEPARTMENTS_ARE_DECISION_AUTHORITIES=true")
print("MODEL_OUTPUT_STATUS=RAW_MATERIAL_ONLY")
print("MEDIA_ADMITTED=false")
print("GENERATION_ADMITTED=false")
print("ENGINE_ADMITTED=false")
PY
