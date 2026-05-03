#!/usr/bin/env bash
set -euo pipefail

test -f scripts/regenerate-object-registry.py
test -f CINEMATICUM_OBJECT_REGISTRY.json
test -f OBJECT_REGISTRY_REGENERATION_GUARD_LAW.json

python3 scripts/regenerate-object-registry.py --check

python3 - <<'PY'
import json
from pathlib import Path

law = json.loads(Path("OBJECT_REGISTRY_REGENERATION_GUARD_LAW.json").read_text(encoding="utf-8"))
assert law["object_type"] == "CINEMATICUM_OBJECT_REGISTRY_REGENERATION_GUARD_LAW"
assert law["guard_owner"] == "scripts/regenerate-object-registry.py"
assert law["freshness_check_owner"] == "scripts/verify-object-registry-fresh.sh"
assert law["registry_owner"] == "CINEMATICUM_OBJECT_REGISTRY.json"
assert law["currently_false_claims"]["release_candidate_ready"] is False
assert law["currently_false_claims"]["issued"] is False
assert law["currently_false_claims"]["media_present"] is False
assert law["currently_false_claims"]["outsider_replay_passed"] is False

registry = json.loads(Path("CINEMATICUM_OBJECT_REGISTRY.json").read_text(encoding="utf-8"))
paths = {entry["path"] for entry in registry["entries"]}
assert "OBJECT_REGISTRY_REGENERATION_GUARD_LAW.json" in paths
assert "CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json" in paths

print("CINEMATICUM OBJECT REGISTRY FRESHNESS: PASS")
PY
