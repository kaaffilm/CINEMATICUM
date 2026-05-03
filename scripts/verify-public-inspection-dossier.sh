#!/usr/bin/env bash
set -euo pipefail

test -f PUBLIC_INSPECTION_DOSSIER_LAW.json
test -f PUBLIC_INSPECTION_DOSSIER.json
test -f PUBLIC_INSPECTION.md
test -f CASES/CASE_001_THE_LAST_RENDER/PUBLIC_INSPECTION_PATH.json

python3 - <<'PY'
import json
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("PUBLIC_INSPECTION_DOSSIER_LAW.json")
dossier = load("PUBLIC_INSPECTION_DOSSIER.json")
case_path = load("CASES/CASE_001_THE_LAST_RENDER/PUBLIC_INSPECTION_PATH.json")
seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert law["object_type"] == "CINEMATICUM_PUBLIC_INSPECTION_DOSSIER_LAW"
assert law["dossier_owner"] == "PUBLIC_INSPECTION_DOSSIER.json"
assert law["public_document_owner"] == "PUBLIC_INSPECTION.md"
assert law["dossier_must_assert"]["private_access_required"] is False
assert law["dossier_must_assert"]["verify_all_pass_required"] is True
assert law["dossier_must_assert"]["object_registry_fresh_required"] is True

assert dossier["object_type"] == "CINEMATICUM_PUBLIC_INSPECTION_DOSSIER"
assert dossier["surface_type"] == "PUBLIC_INSPECTION_DOSSIER"
assert dossier["private_access_required"] is False
assert dossier["case_id"] == "CASE_001_THE_LAST_RENDER"
assert dossier["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert "bash scripts/verify-all.sh" in dossier["inspection_commands"]
assert "bash scripts/verify-public-inspection-dossier.sh" in dossier["inspection_commands"]

for key in [
    "release_candidate_ready",
    "issued",
    "media_present",
    "generation_present",
    "engine_present",
    "model_present",
    "outsider_replay_passed",
    "admissibility_verdict_present",
    "terminal_closure_present"
]:
    assert dossier["expected_current_claims"][key] is False, key

assert case_path["private_access_required"] is False
assert case_path["current_state"] == dossier["current_state"]
assert case_path["release_candidate_ready"] is False
assert case_path["issued"] is False
assert case_path["media_present"] is False
assert case_path["outsider_replay_passed"] is False

assert seal["current_state"] == dossier["current_state"]
assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == dossier["current_state"]
assert case["current_state"] == dossier["current_state"]
assert registry["current_active_state"] == dossier["current_state"]

text = Path("PUBLIC_INSPECTION.md").read_text(encoding="utf-8")
for needle in [
    "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED",
    "release_candidate_ready=false",
    "issued=false",
    "media_present=false",
    "outsider_replay_passed=false",
    "bash scripts/verify-all.sh",
    "does not issue a film",
    "does not admit media"
]:
    assert needle in text, needle

print("CINEMATICUM PUBLIC INSPECTION DOSSIER: PASS")
print("PRIVATE_ACCESS_REQUIRED=false")
print("ACTIVE_CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("RELEASE_CANDIDATE_READY=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
print("REPLAY_PASSED=false")
PY
