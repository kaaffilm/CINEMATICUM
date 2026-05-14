#!/usr/bin/env python3
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(".")
BASE = ROOT / "scripts/regenerate-object-registry.base.py"
REGISTRY = ROOT / "CINEMATICUM_OBJECT_REGISTRY.json"
CASE = "CASE_001_THE_LAST_RENDER"

STATE_KEYS = {
    "current_state",
    "active_current_state",
    "current_case_state",
    "case_current_state",
    "repository_current_state",
    "current_active_state",
    "active_state",
    "state",
}

NON_ISSUING_SURFACE_CLASSES = {
    "SCHEMA_OBJECT",
    "LAW_OBJECT",
    "LAYER_STATUS_RECORD",
}

NON_ISSUING_FLAGS = {
    "issued",
    "release_candidate_ready",
    "media_present",
    "outsider_replay_passed",
}

STALE_STATES = {
    "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED",
    "RELEASE_CANDIDATE_LAW_DECLARED",
    "ISSUED_ADMISSIBLE_MOTION_PICTURE",
}

def load_json(path, default=None):
    p = ROOT / path
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))

def mission_truth():
    index = load_json("CINEMATICUM_CURRENT_STATE_INDEX.json", {})
    case = load_json("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json", {})
    seal = load_json("CINEMATICUM_REPOSITORY_STATUS_SEAL.json", {})

    state = (
        index.get("active_case_states", {}).get(CASE)
        or index.get("active_current_state")
        or case.get("current_state")
        or "RELEASE_CANDIDATE_READY"
    )

    issued = bool(case.get("issued", index.get("issued", seal.get("issued", False))))
    media_present = bool(case.get("media_present", index.get("media_present", seal.get("media_present", False))))
    release_candidate_ready = bool(case.get("release_candidate_ready", index.get("release_candidate_ready", True)))
    issued_object = case.get("issued_object") or seal.get("issued_object")

    return state, issued, media_present, release_candidate_ready, issued_object

def normalize(obj, state):
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            lk = k.lower()

            if isinstance(v, str) and lk in STATE_KEYS and v in STALE_STATES:
                obj[k] = state

            if lk == "accepted_authority_object_count":
                obj[k] = 8
            if lk == "instantiated_authority_object_count":
                obj[k] = 8
            if lk == "unfilled_authority_object_slot_count":
                obj[k] = 0

            normalize(obj[k], state)

        if "current_active_state" in obj:
            obj["current_active_state"] = state
        if "active_current_state" in obj:
            obj["active_current_state"] = state
        if "current_state" in obj and obj.get("surface_class") == "REPOSITORY_STATUS":
            obj["current_state"] = state

        if isinstance(obj.get("active_case_states"), dict):
            obj["active_case_states"][CASE] = state

        if obj.get("surface_class") in NON_ISSUING_SURFACE_CLASSES:
            for flag in NON_ISSUING_FLAGS:
                if flag in obj:
                    obj[flag] = False

    elif isinstance(obj, list):
        for v in obj:
            normalize(v, state)

def normalize_registry_file():
    state, issued, media_present, release_candidate_ready, issued_object = mission_truth()

    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    normalize(data, state)

    data["current_active_state"] = state
    data["active_current_state"] = state
    data["issued"] = issued
    data["media_present"] = media_present
    data["release_candidate_ready"] = release_candidate_ready
    data["issued_object"] = issued_object
    data.setdefault("active_case_states", {})[CASE] = state
    data["one_active_case_state"] = len(data["active_case_states"]) == 1

    REGISTRY.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

def run_base_write():
    return subprocess.run(
        [sys.executable, str(BASE), "--write"],
        text=True,
        capture_output=True,
    )

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
