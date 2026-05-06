#!/usr/bin/env bash
set -euo pipefail

test -f OUTSIDER_CLONE_REPLAY_LAW.json
test -f OUTSIDER_CLONE_REPLAY.json
test -f OUTSIDER_CLONE_REPLAY.md
test -f CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_CLONE_REPLAY_STATUS.json

python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path(".")

def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

law = load("OUTSIDER_CLONE_REPLAY_LAW.json")
replay = load("OUTSIDER_CLONE_REPLAY.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_CLONE_REPLAY_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
required = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
manifest = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

expected_state = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"

assert law["object_type"] == "CINEMATICUM_OUTSIDER_CLONE_REPLAY_LAW"
assert law["replay_owner"] == "OUTSIDER_CLONE_REPLAY.json"
assert law["public_document_owner"] == "OUTSIDER_CLONE_REPLAY.md"
assert law["status_owner"] == "CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_CLONE_REPLAY_STATUS.json"
assert law["required_primary_command"] == "bash scripts/verify-all.sh"
assert law["required_local_command"] == "bash scripts/verify-outsider-clone-replay.sh"
assert law["current_state_locked_to"] == expected_state

for key, value in law["clone_replay_must_assert"].items():
    if key in {
        "media_or_model_payload_present"
    }:
        assert value is False, key
    else:
        assert value is True if key not in {
            "private_access_required",
            "network_required_after_clone"
        } else value is False, key

assert replay["object_type"] == "CINEMATICUM_OUTSIDER_CLONE_REPLAY"
assert replay["current_state"] == expected_state
assert replay["private_access_required"] is False
assert replay["network_required_after_clone"] is False
assert replay["media_required"] is False
assert replay["model_required"] is False
assert replay["paid_api_required"] is False
assert replay["cloud_render_required"] is False
assert replay["verification_command"] == "bash scripts/verify-all.sh"
assert replay["local_harness_command"] == "bash scripts/verify-outsider-clone-replay.sh"

for doc in [
    "PUBLIC_INSPECTION.md",
    "PUBLIC_STATUS.md",
    "PUBLIC_NEGATIVE_PROOF.md",
    "PUBLIC_PERIMETER_SENTINEL.md",
    "OUTSIDER_CLONE_REPLAY.md",
]:
    assert doc in replay["public_start_documents"], doc
    assert (ROOT / doc).exists(), doc

for owner in replay["truth_owners"]:
    assert (ROOT / owner).exists(), owner

for key, value in replay["expected_false_claims"].items():
    assert value is False, key

assert status["object_type"] == "CINEMATICUM_CASE_OUTSIDER_CLONE_REPLAY_STATUS"
assert status["case_id"] == "CASE_001_THE_LAST_RENDER"
assert status["current_state"] == expected_state
assert status["fresh_checkout_can_verify"] is True
assert status["private_access_required"] is False
assert status["network_required_after_clone"] is False
assert status["media_or_model_payload_present"] is False
assert status["forbidden_private_file_present"] is False
assert status["release_candidate_ready"] is False
assert status["issued"] is False
assert status["media_present"] is False
assert status["outsider_replay_passed"] is False
assert status["valid_transition_attempt_present"] is False
assert status["may_advance_now"] is False
assert status["admissibility_verdict_present"] is False
assert status["terminal_closure_present"] is False

assert index["active_case_states"]["CASE_001_THE_LAST_RENDER"] == expected_state
assert case["current_state"] == expected_state
assert seal["current_state"] == expected_state
assert registry["current_active_state"] == expected_state

assert gate["current_state"] == expected_state
assert gate["may_advance_now"] is False
assert required["required_authority_objects_missing"] is True
assert ledger["valid_transition_attempt_present"] is False
def values_for_key(obj, key):
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.append(v)
            found.extend(values_for_key(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(values_for_key(item, key))
    return found

sentinel_private_access_claims = values_for_key(sentinel, "private_access_required")
sentinel_media_payload_claims = values_for_key(sentinel, "media_or_model_payload_present")

assert sentinel_private_access_claims, "sentinel missing private_access_required claim"
assert sentinel_media_payload_claims, "sentinel missing media_or_model_payload_present claim"
assert all(v is False for v in sentinel_private_access_claims if isinstance(v, bool))
assert all(v is False for v in sentinel_media_payload_claims if isinstance(v, bool))

assert "scripts/verify-outsider-clone-replay.sh" in manifest["required_scripts"]
assert "tests/test_outsider_clone_replay.py" in manifest["required_unittests"]
assert "outsider-clone-replay" in manifest["required_ci_workflows"]
assert "outsider_clone_replay_requires_no_private_access" in manifest["master_invariants"]

text = Path("OUTSIDER_CLONE_REPLAY.md").read_text(encoding="utf-8")
for needle in [
    "git clone https://github.com/kaaffilm/CINEMATICUM.git",
    "bash scripts/verify-all.sh",
    "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS",
    "release_candidate_ready=false",
    "issued=false",
    "media_present=false",
    "does not issue a film",
    "does not admit media",
    "does not create terminal closure",
]:
    assert needle in text, needle

verify_all = Path("scripts/verify-all.sh").read_text(encoding="utf-8")
assert "bash scripts/verify-outsider-clone-replay.sh" in verify_all
assert "python3 -m unittest tests/test_outsider_clone_replay.py" in verify_all

print("CINEMATICUM OUTSIDER CLONE REPLAY: PASS")
print("CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
print("FRESH_CHECKOUT_CAN_VERIFY=true")
print("PRIVATE_ACCESS_REQUIRED=false")
print("NETWORK_REQUIRED_AFTER_CLONE=false")
print("MEDIA_OR_MODEL_PAYLOAD_PRESENT=false")
print("ISSUED=false")
print("MEDIA_PRESENT=false")
PY

FORBIDDEN_FILES="$(find . -type f \
  \( -iname '.env' -o -iname '.env.*' -o -iname '*.pem' -o -iname '*.key' -o -iname '*.p12' -o -iname '*.pfx' -o -iname '*token*' -o -iname '*secret*' -o -iname '*credential*' \) \
  -not -path './.git/*' | sort || true)"

if test -n "$FORBIDDEN_FILES"; then
  printf "forbidden private file found:\n%s\n" "$FORBIDDEN_FILES" >&2
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
