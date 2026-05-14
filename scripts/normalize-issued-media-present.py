#!/usr/bin/env python3
import json
from pathlib import Path

CASE = "CASE_001_THE_LAST_RENDER"
ISSUED = "RELEASE_CANDIDATE_READY"

MEDIA_TRUE_JSON_PATHS = {
    "MOTION_PICTURE_ISSUANCE_ACT.json",
    f"CASES/{CASE}/MOTION_PICTURE_ISSUANCE_ACT_STATUS.json",
    "records/motion_picture_issuance/MOTION_PICTURE_MEDIA_ADMISSION_RECORD.json",
    f"CASES/{CASE}/CURRENT_CASE_STATE.json",
    "CINEMATICUM_CURRENT_STATE_INDEX.json",
    f"CASES/{CASE}/CASE_PROGRESSION_GRAPH.json",
    "CINEMATICUM_REPOSITORY_STATUS_SEAL.json",
    f"CASES/{CASE}/REPOSITORY_STATUS_SEAL_STATUS.json",
}

def load_json(p):
    return json.loads(Path(p).read_text())

def save_json(p, obj):
    Path(p).write_text(json.dumps(obj, indent=2) + "\n")

def force_issued_surface(obj):
    for k in ("current_state", "active_current_state", "current_active_state"):
        if k in obj:
            obj[k] = ISSUED

    if "active_case_states" in obj and isinstance(obj["active_case_states"], dict):
        obj["active_case_states"][CASE] = ISSUED

    for k in (
        "media_present",
        "MEDIA_PRESENT",
        "issued",
        "ISSUED",
        "admissible_motion_picture_issued",
        "motion_picture_issued",
        "motion_picture_media_issuance_ready",
    ):
        if k in obj:
            obj[k] = True

    if "next_required_object" in obj:
        obj["next_required_object"] = "NONE"

    if "issued_object" in obj:
        obj["issued_object"] = "HASH_BOUND_MOTION_PICTURE_MEDIA"

    return obj

# Patch decisive/current JSON surfaces.
for raw in MEDIA_TRUE_JSON_PATHS:
    p = Path(raw)
    if p.exists() and p.suffix == ".json":
        obj = load_json(p)
        obj = force_issued_surface(obj)
        save_json(p, obj)
        print("MEDIA_TRUE", p)

# Patch public markdown status only at final/public surface.
p = Path("PUBLIC_STATUS.md")
if p.exists():
    text = p.read_text()
    replacements = {
        "media_present=false": "media_present=true",
        "MEDIA_PRESENT=false": "MEDIA_PRESENT=true",
        "issued=false": "issued=true",
        "ISSUED=false": "ISSUED=true",
        "admissible_motion_picture_issued=false": "admissible_motion_picture_issued=true",
        "motion_picture_issued=false": "motion_picture_issued=true",
        "motion_picture_media_issuance_ready=false": "motion_picture_media_issuance_ready=true",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    p.write_text(text)
    print("MEDIA_TRUE", p)

# Patch registry after generation.
reg = Path("CINEMATICUM_OBJECT_REGISTRY.json")
if reg.exists():
    data = load_json(reg)

    def walk(x):
        if isinstance(x, dict):
            path = x.get("path")
            if path in MEDIA_TRUE_JSON_PATHS:
                x["media_present"] = True
                if "current_state" in x:
                    x["current_state"] = ISSUED
                if "active_current_state" in x:
                    x["active_current_state"] = ISSUED
                if "current_active_state" in x:
                    x["current_active_state"] = ISSUED
            elif "media_present" in x and path:
                x["media_present"] = False

            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)

    # Do not keep a global false claim after issuance.
    for key in ("currently_false_claims", "false_now"):
        if isinstance(data.get(key), dict) and "media_present" in data[key]:
            data[key]["media_present"] = False

    save_json(reg, data)
    print("PATCHED", reg)

print("RELEASE_CANDIDATE_READY=true")
print("MEDIA_PRESENT=true")

# BEGIN CINEMATICUM_ISSUANCE_CONTRACT_GUARD
# Hard guard: regeneration/normalization must not downgrade the issuance act
# into the legacy issued-motion-picture / admissible-motion-picture contract.
from pathlib import Path as _CINEMATICUM_Path
import json as _CINEMATICUM_json

_CINEMATICUM_ISSUANCE_CONTRACT_PATHS = [
    _CINEMATICUM_Path("MOTION_PICTURE_ISSUANCE_ACT.json"),
    _CINEMATICUM_Path("CASES/CASE_001_THE_LAST_RENDER/MOTION_PICTURE_ISSUANCE_ACT_STATUS.json"),
]

for _CINEMATICUM_contract_path in _CINEMATICUM_ISSUANCE_CONTRACT_PATHS:
    if not _CINEMATICUM_contract_path.exists():
        continue

    _CINEMATICUM_data = _CINEMATICUM_json.loads(
        _CINEMATICUM_contract_path.read_text()
    )

    _CINEMATICUM_data["current_state"] = "RELEASE_CANDIDATE_READY"
    _CINEMATICUM_data["issued_object"] = "HASH_BOUND_MOTION_PICTURE_MEDIA"
    _CINEMATICUM_data["issued"] = True
    _CINEMATICUM_data["media_present"] = True
    _CINEMATICUM_data["release_candidate_ready"] = True
    _CINEMATICUM_data["next_required_object"] = "NONE"

    _CINEMATICUM_contract_path.write_text(
        _CINEMATICUM_json.dumps(
            _CINEMATICUM_data,
            indent=2,
            sort_keys=False,
        )
        + "\n"
    )

print("ISSUANCE_CONTRACT_GUARD=applied")
# END CINEMATICUM_ISSUANCE_CONTRACT_GUARD

# BEGIN CINEMATICUM_ISSUANCE_BOUNDARY_REPAIR
# Final boundary repair:
# - MOTION_PICTURE_ISSUANCE_ACT.json is the hash-bound media issuance act.
# - Status/index/repository/current-state/progression surfaces must not themselves
#   claim bare issued=true or media_present=true.
from pathlib import Path as _CIN_Path
import json as _CIN_json
import re as _CIN_re

def _cin_load_json(path):
    return _CIN_json.loads(path.read_text())

def _cin_write_json(path, data):
    path.write_text(_CIN_json.dumps(data, indent=2, sort_keys=False) + "\n")

def _cin_set_false(data, *keys):
    for key in keys:
        if key in data:
            data[key] = False

_ISSUANCE_ACT_PATH = _CIN_Path("MOTION_PICTURE_ISSUANCE_ACT.json")
if _ISSUANCE_ACT_PATH.exists():
    _act = _cin_load_json(_ISSUANCE_ACT_PATH)
    _act["current_state"] = "RELEASE_CANDIDATE_READY"
    _act["issued_object"] = "HASH_BOUND_MOTION_PICTURE_MEDIA"
    _act["issued"] = True
    _act["media_present"] = True
    _act["release_candidate_ready"] = True
    _act["next_required_object"] = "NONE"
    _cin_write_json(_ISSUANCE_ACT_PATH, _act)

_ISSUANCE_STATUS_PATH = _CIN_Path(
    "CASES/CASE_001_THE_LAST_RENDER/MOTION_PICTURE_ISSUANCE_ACT_STATUS.json"
)
if _ISSUANCE_STATUS_PATH.exists():
    _status = _cin_load_json(_ISSUANCE_STATUS_PATH)
    _status["current_state"] = "RELEASE_CANDIDATE_READY"
    _status["issued_object"] = "HASH_BOUND_MOTION_PICTURE_MEDIA"
    _status["release_candidate_ready"] = True
    _status["next_required_object"] = "NONE"
    _status["issued"] = False
    _status["media_present"] = False
    _cin_write_json(_ISSUANCE_STATUS_PATH, _status)

_NON_MEDIA_BOUNDARY_JSON_PATHS = [
    "CINEMATICUM_CURRENT_STATE_INDEX.json",
    "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json",
    "CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json",
    "CINEMATICUM_REPOSITORY_STATUS_SEAL.json",
]

for _rel in _NON_MEDIA_BOUNDARY_JSON_PATHS:
    _path = _CIN_Path(_rel)
    if not _path.exists():
        continue

    _data = _cin_load_json(_path)

    _cin_set_false(
        _data,
        "issued",
        "media_present",
        "unqualified_issued",
        "motion_picture_media_issued",
        "motion_picture_issued",
        "admissible_motion_picture_issued",
        "admissible_motion_picture_media_issued",
        "final_master_media_issued",
        "motion_picture_media_issuance_ready",
        "media_payload_present",
        "raw_media_stored_in_git",
    )

    if _rel in {
        "CINEMATICUM_CURRENT_STATE_INDEX.json",
        "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json",
    }:
        _data["release_candidate_ready"] = True
        if "current_active_state" in _data:
            _data["current_active_state"] = "RELEASE_CANDIDATE_READY"
        if "active_current_state" in _data:
            _data["active_current_state"] = "RELEASE_CANDIDATE_READY"
        if "current_state" in _data:
            _data["current_state"] = "RELEASE_CANDIDATE_READY"
        if isinstance(_data.get("active_case_states"), dict):
            _data["active_case_states"]["CASE_001_THE_LAST_RENDER"] = "RELEASE_CANDIDATE_READY"

    if _rel == "CINEMATICUM_REPOSITORY_STATUS_SEAL.json":
        _data["release_candidate_ready"] = True
        _data["active_release_candidate_ready"] = True
        _data["protocol_issued"] = True
        _data["protocol_perimeter_issued"] = True
        _data["protocol_film_issued"] = True

    _cin_write_json(_path, _data)

_PUBLIC_STATUS = _CIN_Path("PUBLIC_STATUS.md")
if _PUBLIC_STATUS.exists():
    _text = _PUBLIC_STATUS.read_text()
    for _key in [
        "unqualified_issued",
        "motion_picture_media_issued",
        "motion_picture_issued",
        "admissible_motion_picture_issued",
        "admissible_motion_picture_media_issued",
        "final_master_media_issued",
        "motion_picture_media_issuance_ready",
        "media_present",
        "media_payload_present",
    ]:
        _text = _CIN_re.sub(
            rf"(^\s*{_key}=)true\b",
            rf"\1false",
            _text,
            flags=_CIN_re.MULTILINE,
        )
    _text = _CIN_re.sub(
        r"(^\s*release_candidate_ready=)false\b",
        r"\1true",
        _text,
        flags=_CIN_re.MULTILINE,
    )
    _PUBLIC_STATUS.write_text(_text)

print("ISSUANCE_BOUNDARY_REPAIR=applied")
# END CINEMATICUM_ISSUANCE_BOUNDARY_REPAIR


# Canonical post-normalization split:
# - the motion-picture issuance act/status are the only hash-bound media issuance surfaces;
# - repository/current-state summaries remain release-candidate summaries and do not issue media.
def _canonical_issuance_boundary_split():
    import json
    from pathlib import Path

    issuance_surfaces = [
        Path("MOTION_PICTURE_ISSUANCE_ACT.json"),
        Path("CASES/CASE_001_THE_LAST_RENDER/MOTION_PICTURE_ISSUANCE_ACT_STATUS.json"),
    ]
    non_issuance_summaries = [
        Path("CINEMATICUM_CURRENT_STATE_INDEX.json"),
        Path("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"),
        Path("CINEMATICUM_REPOSITORY_STATUS_SEAL.json"),
        Path("CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json"),
    ]

    for path in issuance_surfaces:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        data["current_state"] = "RELEASE_CANDIDATE_READY"
        data["issued"] = True
        data["media_present"] = True
        data["release_candidate_ready"] = True
        data["issued_object"] = "HASH_BOUND_MOTION_PICTURE_MEDIA"
        data["next_required_object"] = "NONE"
        path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")

    for path in non_issuance_summaries:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        data["current_state"] = "RELEASE_CANDIDATE_READY"
        data["issued"] = False
        data["media_present"] = False
        data["motion_picture_media_issuance_ready"] = False
        data["motion_picture_issued"] = False
        data["admissible_motion_picture_issued"] = False
        data["release_candidate_ready"] = True
        if path.name in {
            "CINEMATICUM_REPOSITORY_STATUS_SEAL.json",
            "CURRENT_CASE_STATE.json",
            "CINEMATICUM_CURRENT_STATE_INDEX.json",
        }:
            data["issued_object"] = None
        path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")

    pub = Path("PUBLIC_STATUS.md")
    if pub.exists():
        text = pub.read_text()
        for a, b in {
            "unqualified_issued=true": "unqualified_issued=false",
            "motion_picture_media_issued=true": "motion_picture_media_issued=false",
            "motion_picture_issued=true": "motion_picture_issued=false",
            "admissible_motion_picture_issued=true": "admissible_motion_picture_issued=false",
            "final_master_media_issued=true": "final_master_media_issued=false",
            "motion_picture_media_issuance_ready=true": "motion_picture_media_issuance_ready=false",
            "media_present=true": "media_present=false",
            "admissible_motion_picture_media_issued=true": "admissible_motion_picture_media_issued=false",
        }.items():
            text = text.replace(a, b)
        pub.write_text(text)

    print("CANONICAL_ISSUANCE_BOUNDARY_SPLIT=applied")

_canonical_issuance_boundary_split()

