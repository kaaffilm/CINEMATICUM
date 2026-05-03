#!/usr/bin/env bash
set -euo pipefail

test -f CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE_LAW.json
test -f CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE.json
test -f MASTER_VERIFICATION_MANIFEST_CLOSURE.md
test -f CASES/CASE_001_THE_LAST_RENDER/MASTER_VERIFICATION_MANIFEST_CLOSURE_STATUS.json
test -f CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json
test -x scripts/verify-all.sh

python3 - <<'PY'
import json
import re
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

law = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE_LAW.json")
closure = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/MASTER_VERIFICATION_MANIFEST_CLOSURE_STATUS.json")
manifest = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

assert law["object_type"] == "CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE_LAW"
assert law["closure_owner"] == "CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE.json"
assert law["manifest_owner"] == "CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json"
assert law["verify_all_owner"] == "scripts/verify-all.sh"
assert law["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"

for key, expected in law["closure_must_assert"].items():
    assert expected is True, key
assert law["closure_must_assert"]["verify_all_self_reference_exempt"] is True

for key, expected in law["currently_false_claims"].items():
    assert expected is False, key

assert closure["object_type"] == "CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE"
assert closure["surface_type"] == "MASTER_VERIFICATION_MANIFEST_CLOSURE"
assert closure["case_id"] == "CASE_001_THE_LAST_RENDER"
assert closure["current_state"] == "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
assert closure["current_truth_owner"] is False

for key, expected in closure["closure_checks"].items():
    assert expected is True, key
assert closure["closure_checks"]["verify_all_self_reference_exempt"] is True

for key, expected in closure["closure_boundaries"].items():
    assert expected is True, key

assert status["object_type"] == "CINEMATICUM_CASE_MASTER_VERIFICATION_MANIFEST_CLOSURE_STATUS"
assert status["surface_type"] == "LAYER_STATUS_RECORD"
assert status["current_truth_owner"] is False

for key in [
    "manifest_present",
    "verify_all_present",
    "all_required_scripts_exist",
    "all_required_scripts_executable",
    "all_required_scripts_in_verify_all",
    "verify_all_self_reference_exempt",
    "verify_all_membership_exempt_scripts_declared",
    "registry_generator_exempt_from_verify_all_membership",
    "all_required_unittests_exist",
    "all_required_unittests_in_verify_all",
    "all_required_ci_workflows_exist"
]:
    assert status[key] is True, key

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
    assert closure["current_false_values"][key] is False, key
    assert status[key] is False, key

current = closure["current_state"]
assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == current
assert case["current_state"] == current
assert registry["current_active_state"] == current

required_scripts = list(dict.fromkeys(manifest.get("required_scripts", [])))
required_tests = list(dict.fromkeys(manifest.get("required_unittests", [])))
required_workflows = list(dict.fromkeys(manifest.get("required_ci_workflows", [])))
verify_all_membership_exempt_scripts = set(closure.get("verify_all_membership_exempt_scripts", []))
assert verify_all_membership_exempt_scripts == {
    "scripts/verify-all.sh",
    "scripts/regenerate-object-registry.py",
}
assert set(law["verify_all_membership_exempt_scripts"]) == verify_all_membership_exempt_scripts
assert set(status["verify_all_membership_exempt_scripts"]) == verify_all_membership_exempt_scripts

assert "scripts/verify-master-verification-manifest-closure.sh" in required_scripts
assert "tests/test_master_verification_manifest_closure.py" in required_tests
assert "master-verification-manifest-closure" in required_workflows

verify_all = Path("scripts/verify-all.sh").read_text(encoding="utf-8")

for script in required_scripts:
    path = Path(script)
    assert path.exists(), script
    assert path.is_file(), script
    if script.startswith("scripts/"):
        assert path.stat().st_mode & 0o111, f"not executable: {script}"
    if script not in verify_all_membership_exempt_scripts:
        assert script in verify_all, script

for test in required_tests:
    path = Path(test)
    assert path.exists(), test
    assert path.is_file(), test
    assert test in verify_all, test

workflow_files = sorted(Path(".github/workflows").glob("*.yml")) + sorted(Path(".github/workflows").glob("*.yaml"))
workflow_stems = {p.stem for p in workflow_files}
workflow_names = set()
for path in workflow_files:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        m = re.match(r"^\s*name:\s*[\"']?([^\"'#]+)[\"']?\s*(?:#.*)?$", line)
        if m:
            workflow_names.add(m.group(1).strip())
            break

for workflow in required_workflows:
    assert workflow in workflow_stems or workflow in workflow_names, workflow

# verify-all should end with the canonical PASS emission.
assert 'CINEMATICUM VERIFY ALL: PASS' in verify_all

text = Path("MASTER_VERIFICATION_MANIFEST_CLOSURE.md").read_text(encoding="utf-8")
for needle in [
    "manifest_present=true",
    "verify_all_present=true",
    "all_required_scripts_exist=true",
    "all_required_scripts_executable=true",
    "all_required_scripts_in_verify_all=true",
    "verify_all_self_reference_exempt=true",
    "verify_all_membership_exempt_scripts_declared=true",
    "registry_generator_exempt_from_verify_all_membership=true",
    "all_required_unittests_exist=true",
    "all_required_unittests_in_verify_all=true",
    "all_required_ci_workflows_exist=true",
    "object_registry_fresh_required=true",
    "verify_all_required=true",
    "release_candidate_ready=false",
    "issued=false",
    "media_present=false",
    "does not issue a film",
    "does not admit media",
    "does not advance state"
]:
    assert needle in text, needle

print("CINEMATICUM MASTER VERIFICATION MANIFEST CLOSURE: PASS")
print("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
print("MANIFEST_PRESENT=true")
print("VERIFY_ALL_PRESENT=true")
print("ALL_REQUIRED_SCRIPTS_EXIST=true")
print("ALL_REQUIRED_SCRIPTS_IN_VERIFY_ALL=true")
print("ALL_REQUIRED_UNITTESTS_EXIST=true")
print("ALL_REQUIRED_UNITTESTS_IN_VERIFY_ALL=true")
print("ALL_REQUIRED_CI_WORKFLOWS_EXIST=true")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY

FORBIDDEN_PRIVATE_FILES="$(find . -type f \
  \( -iname '.env' -o -iname '.env.*' -o -iname '*.pem' -o -iname '*.key' -o -iname '*.p12' -o -iname '*.pfx' -o -iname '*token*' -o -iname '*secret*' -o -iname '*credential*' \) \
  -not -path './.git/*' | sort || true)"

if test -n "$FORBIDDEN_PRIVATE_FILES"; then
  printf "forbidden private file found:\n%s\n" "$FORBIDDEN_PRIVATE_FILES" >&2
  exit 1
fi

MEDIA_OR_MODEL="$(find . -type f \
  \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.avi' -o -iname '*.mkv' -o -iname '*.webm' \
     -o -iname '*.wav' -o -iname '*.aiff' -o -iname '*.flac' -o -iname '*.mp3' \
     -o -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.tiff' -o -iname '*.exr' -o -iname '*.dpx' \
     -o -iname '*.ckpt' -o -iname '*.safetensors' -o -iname '*.onnx' -o -iname '*.pt' -o -iname '*.pth' -o -iname '*.gguf' \) \
  -not -path './.git/*' | sort || true)"

if test -n "$MEDIA_OR_MODEL"; then
  printf "forbidden media/model artifact found:\n%s\n" "$MEDIA_OR_MODEL" >&2
  exit 1
fi
