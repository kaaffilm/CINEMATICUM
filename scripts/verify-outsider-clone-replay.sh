#!/usr/bin/env bash
set -euo pipefail

"${PYTHON:-python3}" - <<'PY2'
import json
from pathlib import Path

CASE = "CASE_001_THE_LAST_RENDER"

# Historical replay record state.
RECORD_TARGET = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"

# Live active case state.
ACTIVE_TARGET = "RELEASE_CANDIDATE_READY"


def check(label, actual, expected):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def check_is(label, actual, expected):
    if actual is not expected:
        raise AssertionError(f"{label}: expected identity {expected!r}, got {actual!r}")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


clone = load("OUTSIDER_CLONE_REPLAY.json")
cin_clone = load("CINEMATICUM_OUTSIDER_CLONE_REPLAY.json")
law = load("OUTSIDER_CLONE_REPLAY_LAW.json")
status = load("CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_CLONE_REPLAY_STATUS.json")
index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
sentinel = load("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json")
registry = load("CINEMATICUM_OBJECT_REGISTRY.json")
protocol_issuance = load("CINEMATICUM_PROTOCOL_ISSUANCE.json")

check("clone equals cin_clone", clone, cin_clone)
check("clone.object_type", clone["object_type"], "CINEMATICUM_OUTSIDER_CLONE_REPLAY")
check("law.object_type", law["object_type"], "CINEMATICUM_OUTSIDER_CLONE_REPLAY_LAW")
check("status.status", status["status"], "PASS")

for obj in (clone, law, status):
    label = obj.get("object_type", "obj")

    check(f"{label}.case_id", obj["case_id"], CASE)
    check(f"{label}.current_state", obj["current_state"], RECORD_TARGET)

    check_is(f"{label}.fresh_checkout_can_verify", obj["fresh_checkout_can_verify"], True)
    check_is(f"{label}.private_access_required", obj["private_access_required"], False)
    check_is(f"{label}.network_required_after_clone", obj["network_required_after_clone"], False)
    check_is(f"{label}.media_or_model_payload_present", obj["media_or_model_payload_present"], False)
    check_is(f"{label}.forbidden_private_file_present", obj["forbidden_private_file_present"], False)
    check_is(f"{label}.valid_transition_attempt_present", obj["valid_transition_attempt_present"], False)

    # Replay proof is not issuance, not media, not a transition grant.
    check_is(f"{label}.release_candidate_ready", obj["release_candidate_ready"], False)
    check_is(f"{label}.release_candidate_artifacts_bound", obj["release_candidate_artifacts_bound"], False)
    check_is(f"{label}.issued", obj["issued"], False)
    check_is(f"{label}.media_present", obj["media_present"], False)
    check_is(f"{label}.outsider_replay_passed", obj["outsider_replay_passed"], False)
    check_is(f"{label}.may_advance_now", obj["may_advance_now"], False)
    check_is(f"{label}.issuance_unblocked", obj["issuance_unblocked"], False)

    # Authority-object stack may be complete while replay still confers no issuance.
    check_is(f"{label}.authority_object_stack_complete", obj["authority_object_stack_complete"], True)
    check(f"{label}.accepted_authority_object_count", obj["accepted_authority_object_count"], 8)
    check(f"{label}.instantiated_authority_object_count", obj["instantiated_authority_object_count"], 8)
    check(f"{label}.unfilled_authority_object_slot_count", obj["unfilled_authority_object_slot_count"], 0)

check("index.active_case_states[CASE]", index["active_case_states"][CASE], ACTIVE_TARGET)
check("case.current_state", case["current_state"], ACTIVE_TARGET)
check("registry.current_active_state", registry["current_active_state"], ACTIVE_TARGET)

check("protocol_issuance.object_type", protocol_issuance["object_type"], "CINEMATICUM_PROTOCOL_ISSUANCE")
check("protocol_issuance.case_id", protocol_issuance["case_id"], CASE)
check_is("protocol_issuance.issued", protocol_issuance["issued"], True)
check_is("protocol_issuance.protocol_perimeter_issued", protocol_issuance["protocol_perimeter_issued"], True)
check_is("protocol_issuance.protocol_film_issued", protocol_issuance["protocol_film_issued"], True)
check("protocol_issuance.issuance_type", protocol_issuance["issuance_type"], "PROTOCOL_FILM")
check("protocol_issuance.issued_object", protocol_issuance["issued_object"], "PUBLIC_REPLAYABLE_HASH_BOUND_PROTOCOL_PERIMETER")
check_is("protocol_issuance.media_payload_present", protocol_issuance["media_payload_present"], False)
check_is("protocol_issuance.private_access_required", protocol_issuance["private_access_required"], False)
check_is("protocol_issuance.fresh_checkout_can_verify", protocol_issuance["fresh_checkout_can_verify"], True)

check_is("sentinel.private_access_required", sentinel["private_access_required"], False)
if "active_current_state" in sentinel:
    check("sentinel.active_current_state", sentinel["active_current_state"], ACTIVE_TARGET)

print("CINEMATICUM OUTSIDER CLONE REPLAY: PASS")
print(f"CURRENT_STATE={RECORD_TARGET}")
print(f"ACTIVE_CURRENT_STATE={ACTIVE_TARGET}")
print("FRESH_CHECKOUT_CAN_VERIFY=true")
print("PRIVATE_ACCESS_REQUIRED=false")
print("NETWORK_REQUIRED_AFTER_CLONE=false")
print("MEDIA_OR_MODEL_PAYLOAD_PRESENT=false")
print("VALID_TRANSITION_ATTEMPT_PRESENT=false")
print("REPLAY_RECORD_RELEASE_CANDIDATE_READY=false")
print("ACTIVE_RELEASE_CANDIDATE_READY=true")
print("REPLAY_RECORD_ISSUED=false")
print("PROTOCOL_PERIMETER_ISSUED=true")
print("ISSUANCE_TYPE=PROTOCOL_FILM")
print("ISSUED=true")
print("MEDIA_PRESENT=false")
PY2

MEDIA_OR_MODEL="$(find . -type f \
  \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.avi' -o -iname '*.mkv' -o -iname '*.webm' \
     -o -iname '*.wav' -o -iname '*.aiff' -o -iname '*.flac' -o -iname '*.mp3' \
     -o -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.tiff' -o -iname '*.exr' -o -iname '*.dpx' \
     -o -iname '*.pt' -o -iname '*.pth' -o -iname '*.ckpt' -o -iname '*.safetensors' -o -iname '*.onnx' \) \
  -not -path './.git/*' \
  -not -path './.venv/*' \
  -not -path './.pytest_cache/*' \
  -not -path './__pycache__/*' \
  -not -path './.cinematicum_media/*' \
  -not -path './cinematicum_closed_pr_dig/*' \
  -print -quit)"

if [ -n "$MEDIA_OR_MODEL" ]; then
  echo "FORBIDDEN_MEDIA_OR_MODEL_PAYLOAD=$MEDIA_OR_MODEL" >&2
  exit 1
fi

exit 0
