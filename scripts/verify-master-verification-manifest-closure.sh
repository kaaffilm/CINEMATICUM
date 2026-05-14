#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
import json
import re
from pathlib import Path

ROOT = Path(".")
CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "RELEASE_CANDIDATE_READY"

MANIFEST = ROOT / "CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json"
VERIFY_ALL = ROOT / "scripts/verify-all.sh"
CURRENT_INDEX = ROOT / "CINEMATICUM_CURRENT_STATE_INDEX.json"
CASE_STATE = ROOT / "CASES" / CASE_ID / "CURRENT_CASE_STATE.json"

assert MANIFEST.exists(), "CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json"
assert VERIFY_ALL.exists(), "scripts/verify-all.sh"
assert CURRENT_INDEX.exists(), "CINEMATICUM_CURRENT_STATE_INDEX.json"
assert CASE_STATE.exists(), f"CASES/{CASE_ID}/CURRENT_CASE_STATE.json"

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

manifest = load_json(MANIFEST)
current_index = load_json(CURRENT_INDEX)
case_state = load_json(CASE_STATE)
verify_all_text = VERIFY_ALL.read_text(encoding="utf-8")

def walk_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for item in node:
            yield from walk_strings(item)
    elif isinstance(node, dict):
        for value in node.values():
            yield from walk_strings(value)

manifest_strings = set(walk_strings(manifest))

def first_flag(*keys, default=None):
    for obj in (manifest, current_index, case_state):
        if not isinstance(obj, dict):
            continue
        for key in keys:
            if key in obj:
                return obj[key]
    return default

def boolish(value):
    return value is True or str(value).lower() == "true"

active_state = (
    first_flag("active_current_state", "current_state", "case_current_state", default=None)
    or current_index.get("active_current_state")
    or current_index.get("current_state")
    or case_state.get("current_state")
    or case_state.get("active_current_state")
)

issued = boolish(first_flag("issued", default=False))
media_present = boolish(first_flag("media_present", default=False))

assert active_state in (
    CURRENT_STATE,
    "ISSUED_ADMISSIBLE_MOTION_PICTURE",
), f"current_state={active_state}"

required_scripts = sorted(s for s in manifest_strings if s.startswith("scripts/verify-") and s.endswith(".sh"))
required_tests = sorted(s for s in manifest_strings if s.startswith("tests/test_") and s.endswith(".py"))

workflow_values = set()
for s in manifest_strings:
    if s.startswith(".github/workflows/") and (s.endswith(".yml") or s.endswith(".yaml")):
        workflow_values.add(s)
    elif s.endswith(".yml") or s.endswith(".yaml"):
        workflow_values.add(s)
    elif re.fullmatch(r"[a-z0-9][a-z0-9-]*", s or "") and (
        "workflow" in s or
        "authority-" in s or
        "cinematic-" in s or
        "object-registry" in s or
        "outsider-" in s or
        "public-" in s or
        "release-" in s or
        "repository-" in s or
        "required-" in s or
        "state-" in s or
        "transition-" in s or
        "master-" in s or
        "current-state" in s
    ):
        workflow_values.add(s)

# Required current layer: force PR29 into the closure surface even if the
# manifest stores the workflow as stem, name, filename, or full path.
required_scripts.append("scripts/verify-authority-object-admission-closure-seal.sh")
required_tests.append("tests/test_authority_object_admission_closure_seal.py")
workflow_values.add("authority-object-admission-closure-seal")

required_scripts = sorted(s for s in set(required_scripts) if s != "scripts/verify-all.sh")
required_tests = sorted(set(required_tests))

for script in required_scripts:
    p = ROOT / script
    assert p.exists(), script
    assert p.is_file(), script
    if script.startswith("scripts/"):
        assert p.stat().st_mode & 0o111, f"not executable: {script}"
    assert script in verify_all_text, script

for test in required_tests:
    p = ROOT / test
    assert p.exists(), test
    assert p.is_file(), test
    assert test in verify_all_text, test

workflow_files = sorted((ROOT / ".github/workflows").glob("*.yml")) + sorted((ROOT / ".github/workflows").glob("*.yaml"))
workflow_tokens = set()

for wf in workflow_files:
    rel = str(wf.relative_to(ROOT)).replace("\\", "/")
    workflow_tokens.add(rel)
    workflow_tokens.add(wf.name)
    workflow_tokens.add(wf.stem)

    text = wf.read_text(encoding="utf-8")
    for line in text.splitlines():
        m = re.match(r"^\s*name:\s*[\"']?([^\"'#]+)[\"']?\s*(?:#.*)?$", line)
        if m:
            name = m.group(1).strip()
            workflow_tokens.add(name)
            workflow_tokens.add(Path(name).name)
            workflow_tokens.add(Path(name).stem)
            break

for workflow in workflow_values:
    workflow_text = str(workflow).replace("\\", "/")
    p = Path(workflow_text)
    candidates = {
        workflow_text,
        p.name,
        p.stem,
    }
    assert candidates & workflow_tokens, workflow

print("CINEMATICUM MASTER VERIFICATION MANIFEST CLOSURE: PASS")
print(f"CURRENT_STATE={CURRENT_STATE}")
print("MANIFEST_PRESENT=true")
print("VERIFY_ALL_PRESENT=true")
print("ALL_REQUIRED_SCRIPTS_EXIST=true")
print("ALL_REQUIRED_SCRIPTS_IN_VERIFY_ALL=true")
print("ALL_REQUIRED_UNITTESTS_EXIST=true")
print("ALL_REQUIRED_UNITTESTS_IN_VERIFY_ALL=true")
print("ALL_REQUIRED_CI_WORKFLOWS_EXIST=true")
print(f"ISSUED={str(issued).lower()}")
print(f"MEDIA_PRESENT={str(media_present).lower()}")
PY

python3 -m unittest tests/test_master_verification_manifest_closure.py
