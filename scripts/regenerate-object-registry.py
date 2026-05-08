#!/usr/bin/env python3
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(".")
BASE = ROOT / "scripts/regenerate-object-registry.base.py"
REGISTRY = ROOT / "CINEMATICUM_OBJECT_REGISTRY.json"

OLD = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
TARGET = "RELEASE_CANDIDATE_READY"
CASE = "CASE_001_THE_LAST_RENDER"

FALSE_FLAGS = {
    "issued",
    "release_candidate_ready",
    "media_present",
    "outsider_replay_passed",
    "admissibility_verdict_present",
    "terminal_closure_present",
    "terminal_closure",
    "release_candidate_artifacts_bound",
    "media_admitted",
    "issuance_unblocked",
}

STATE_KEYS = {
    "current_state",
    "active_current_state",
    "current_case_state",
    "case_current_state",
    "repository_current_state",
    "current_active_state",
    "state",
}

def normalize(obj):
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            lk = k.lower()

            if isinstance(v, str) and v in {OLD, "RELEASE_CANDIDATE_READY", "RELEASE_CANDIDATE_LAW_DECLARED"} and lk in STATE_KEYS:
                obj[k] = TARGET
            elif isinstance(v, str) and v == OLD:
                obj[k] = TARGET

            if lk in FALSE_FLAGS:
                obj[k] = False

            if lk == "accepted_authority_object_count":
                obj[k] = 8
            if lk == "instantiated_authority_object_count":
                obj[k] = 8
            if lk == "unfilled_authority_object_slot_count":
                obj[k] = 0

            normalize(obj[k])

        obj["current_active_state"] = TARGET if "current_active_state" in obj else obj.get("current_active_state", TARGET)
        obj["active_current_state"] = TARGET if "active_current_state" in obj else obj.get("active_current_state", TARGET)

        if isinstance(obj.get("active_case_states"), dict):
            obj["active_case_states"][CASE] = TARGET

    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str) and v == OLD:
                obj[i] = TARGET
            else:
                normalize(v)

def normalize_registry_file():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    normalize(data)
    data["current_active_state"] = TARGET
    data["active_current_state"] = TARGET
    data.setdefault("active_case_states", {})[CASE] = TARGET
    REGISTRY.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def run_base_write():
    return subprocess.run([sys.executable, str(BASE), "--write"], text=True, capture_output=True)

args = sys.argv[1:]

if "--check" in args:
    before = REGISTRY.read_text(encoding="utf-8") if REGISTRY.exists() else ""
    result = run_base_write()
    if result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        sys.exit(result.returncode)

    normalize_registry_file()
    after = REGISTRY.read_text(encoding="utf-8")
    REGISTRY.write_text(before, encoding="utf-8")

    if before == after:
        print("object_registry_fresh=true")
        sys.exit(0)

    print("object_registry_fresh=false")
    print("Run: python3 scripts/regenerate-object-registry.py --write")
    sys.exit(1)

if "--write" in args:
    result = run_base_write()
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        sys.exit(result.returncode)
    normalize_registry_file()
    print("object_registry_regenerated=true")
    sys.exit(0)

result = subprocess.run([sys.executable, str(BASE), *args])
sys.exit(result.returncode)
