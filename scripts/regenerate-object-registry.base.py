#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "CINEMATICUM_OBJECT_REGISTRY.json"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


SURFACE_OVERRIDES = {
    "CINEMATICUM_CURRENT_STATE_INDEX.json": "ACTIVE_CURRENT_STATE",
    "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json": "ACTIVE_CURRENT_STATE",
    "CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json": "VERIFICATION_MANIFEST",
    "CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json": "PROGRESSION_GRAPH",
    "CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json": "PROGRESSION_GRAPH",
}


def classify(path: str, data: dict) -> str:
    if path in SURFACE_OVERRIDES:
        return SURFACE_OVERRIDES[path]
    if data.get("surface_type") == "LAYER_STATUS_RECORD":
        return "LAYER_STATUS_RECORD"
    if data.get("surface_type") == "ACTIVE_CURRENT_STATE":
        return "ACTIVE_CURRENT_STATE"

    object_type = str(data.get("object_type", "")).upper()
    if "SCHEMA" in object_type:
        return "SCHEMA_OBJECT"
    if "LAW" in object_type:
        return "LAW_OBJECT"
    if "STATUS" in object_type:
        return "LAYER_STATUS_RECORD"
    if "MANIFEST" in object_type:
        return "VERIFICATION_MANIFEST"
    if "PROGRESSION" in object_type:
        return "PROGRESSION_GRAPH"
    if "DOCKET" in object_type or "LEDGER" in object_type or "CASE" in object_type:
        return "CASE_RECORD"
    return "CASE_RECORD"


def build_registry() -> dict:
    entries = []

    for p in sorted(ROOT.rglob("*.json")):
        if ".git" in p.parts:
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel == "CINEMATICUM_OBJECT_REGISTRY.json":
            continue

        data = json.loads(p.read_text(encoding="utf-8"))
        surface_class = classify(rel, data)

        entries.append({
            "path": rel,
            "sha256": sha256_path(p),
            "object_type": data.get("object_type", "UNDECLARED_OBJECT_TYPE"),
            "schema_version": data.get("schema_version", "UNDECLARED_SCHEMA_VERSION"),
            "surface_class": surface_class,
            "case_id": data.get("case_id"),
            "current_truth_owner": bool(data.get("surface_type") == "ACTIVE_CURRENT_STATE"),
            "issued": bool(data.get("issued", False)),
            "release_candidate_ready": bool(data.get("release_candidate_ready", False)),
            "media_present": bool(data.get("media_present", False)),
            "outsider_replay_passed": bool(data.get("outsider_replay_passed", False)),
        })

    return {
        "object_type": "CINEMATICUM_OBJECT_REGISTRY",
        "schema_version": "cinematicum.object_registry.v1",
        "institution": "CINEMATICUM",
        "root_sentence": "CINEMATICUM issues admissible motion pictures.",
        "surface_type": "OBJECT_REGISTRY",
        "registry_does_not_issue_film": True,
        "registry_does_not_admit_media": True,
        "registry_does_not_override_current_state": True,
        "current_active_state": "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS",
        "case_id": "CASE_001_THE_LAST_RENDER",
        "entries_count": len(entries),
        "entries": entries,
    }


def canonical(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    generated = canonical(build_registry())

    if args.write:
        REGISTRY_PATH.write_text(generated, encoding="utf-8")
        print("object_registry_regenerated=true")
        return 0

    if args.check:
        existing = REGISTRY_PATH.read_text(encoding="utf-8")
        if existing != generated:
            print("object_registry_fresh=false")
            print("Run: python3 scripts/regenerate-object-registry.py --write")
            return 1
        print("object_registry_fresh=true")
        return 0

    print(generated, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
