"""Production shot plans conformed to actual project-owned footage.

Only the selected JSON and already imported project assets are read. Source
directory/filename hints never become paths to open. A complete, content-bound
cut is returned as an unsaved candidate; no placeholder is created and no case
or film issuance record is changed. This verifies media/timing conformance, not
the artistic realism or admissibility of the selected pictures.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
import re
from pathlib import PurePosixPath

if __package__:
    from .engine import _media_path, validate_project, VIDEO_EXTENSIONS
    from .interchange import _sha256
    from .timebase import parse_rate, project_rate
else:
    from engine import _media_path, validate_project, VIDEO_EXTENSIONS
    from interchange import _sha256
    from timebase import parse_rate, project_rate


MAX_PLAN_BYTES = 2 * 1024 * 1024
MAX_SHOTS = 256
_POLICIES = ("fake_fallback_allowed", "toy_renderer_allowed", "procedural_placeholder_allowed")
_ROOT_KEYS = {"version", "film", "artifact_class", "fps", "frame_rate", "width", "height",
              "runtime_target_seconds", "runtime_frames", "required_source_dir", "shots", *_POLICIES}
_SHOT_KEYS = {"id", "filename", "description", "duration", "duration_seconds", "duration_frames", "start_frame", "sha256"}


def _document(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate production-plan JSON member: " + key[:80])
            result[key] = item
        return result

    def reject_constant(value):
        raise ValueError("Production plans require finite JSON numbers.")

    try:
        if not isinstance(value, (str, bytes)):
            value = json.dumps(value, allow_nan=False, separators=(",", ":"))
        raw = value if isinstance(value, bytes) else value.encode("utf-8")
        if len(raw) > MAX_PLAN_BYTES:
            raise ValueError("The production plan exceeds 2 MiB.")
        result = json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant)
    except (TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid production-plan JSON.") from exc
    pending, count = [(result, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if depth > 12 or count > 12000:
            raise ValueError("Production-plan structure exceeds its bounded limit.")
        if isinstance(node, dict):
            pending.extend((item, depth + 1) for item in node.values())
        elif isinstance(node, list):
            pending.extend((item, depth + 1) for item in node)
    return result


def _text(value, label, maximum, *, empty=False):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value or (not empty and not value.strip()):
        raise ValueError(f"{label} must contain {'0' if empty else '1'}–{maximum} characters.")
    return value


def _identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError(label + " must contain 1–128 letters, numbers, underscores or hyphens.")
    return value


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer from {low} to {high}.")
    return value


def _seconds_frames(value, rate, label):
    # Compare bounded JSON integers before any conversion to float. A valid
    # 1,000-digit integer must be a reported input error, never OverflowError.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 21600:
        raise ValueError(label + " must be finite, positive seconds up to six hours.")
    frames = Fraction(str(value)) * rate.fraction
    nearest = round(frames)
    # Decimal JSON can express an exact frame duration with finite precision.
    # Tolerance is far below a sample at 48 kHz; it is not cadence rounding.
    if abs(frames - nearest) > Fraction(1, 1000000):
        raise ValueError(label + " falls between frames at the declared rate. Supply an explicit integer duration_frames instead.")
    return _integer(nearest, label + " frames", 1, rate.max_timeline_frames(21600))


def normalize_plan(document):
    """Accept the repository shotlist or canonical v1 JSON, without reading media."""
    raw = _document(document)
    if not isinstance(raw, dict) or set(raw) - _ROOT_KEYS:
        raise ValueError("Production plan has unsupported fields or is not an object.")
    if "version" in raw and (type(raw["version"]) is not int or raw["version"] != 1):
        raise ValueError("Production plan requires version 1.")
    if "fps" not in raw and "frame_rate" not in raw:
        raise ValueError("Production plan must declare fps or an exact frame_rate.")
    if "fps" in raw and (isinstance(raw["fps"], bool) or not isinstance(raw["fps"], (int, float))
                         or not 1 <= raw["fps"] <= 60):
        raise ValueError("Plan fps must be a number from 1 to 60; use frame_rate for an exact rational clock.")
    rate = project_rate(raw)
    width = _integer(raw.get("width"), "Plan width", 16, 8192)
    height = _integer(raw.get("height"), "Plan height", 16, 8192)
    if width % 2 or height % 2 or width * height > 33_554_432:
        raise ValueError("Plan dimensions must be even and at most 33.5 million pixels.")
    plan = {"version": 1, "film": _text(raw.get("film"), "Film name", 160),
            "artifact_class": _text(raw.get("artifact_class", "source_shot_film"), "Artifact class", 160),
            "fps": rate.fps, "frame_rate": rate.as_dict(), "width": width, "height": height}
    for flag in _POLICIES:
        if raw.get(flag, False) is not False:
            raise ValueError("Production conformance requires " + flag + " to be false. Missing footage is never replaced.")
        plan[flag] = False
    if "required_source_dir" in raw:
        # Preserve the production hint without resolving, scanning or opening it.
        plan["required_source_dir"] = _text(raw["required_source_dir"], "Source directory hint", 1024)
    shots = raw.get("shots")
    if not isinstance(shots, list) or not 1 <= len(shots) <= MAX_SHOTS:
        raise ValueError(f"Production plan requires 1–{MAX_SHOTS} shots.")
    normalized, ids, filenames, cursor = [], set(), set(), 0
    maximum = rate.max_timeline_frames(21600)
    for item in shots:
        if not isinstance(item, dict) or set(item) - _SHOT_KEYS:
            raise ValueError("A production shot contains unsupported fields or is not an object.")
        ident = _identifier(item.get("id"), "Shot ID")
        name = _text(item.get("filename"), "Shot filename", 255)
        if "/" in name or "\\" in name or PurePosixPath(name).suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError("Shot filename must be a video basename, never a path or web address.")
        if ident in ids or name in filenames:
            raise ValueError("Production shot IDs and filenames must be unique.")
        ids.add(ident)
        filenames.add(name)
        durations = []
        if "duration_frames" in item:
            durations.append(_integer(item["duration_frames"], "Shot duration_frames", 1, maximum))
        for key in ("duration", "duration_seconds"):
            if key in item:
                durations.append(_seconds_frames(item[key], rate, "Shot " + ident + " duration"))
        if not durations or any(duration != durations[0] for duration in durations):
            raise ValueError("Shot " + ident + " requires a duration and all supplied durations must agree.")
        duration = durations[0]
        if "start_frame" in item and _integer(item["start_frame"], "Shot start_frame", 0, maximum) != cursor:
            raise ValueError("Shot start_frame conflicts with the ordered continuous production cut.")
        shot = {"id": ident, "filename": name, "description": _text(item.get("description", ""), "Shot description", 4000, empty=True),
                "start_frame": cursor, "duration_frames": duration}
        if "sha256" in item:
            if not isinstance(item["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
                raise ValueError("Shot SHA-256 must be a lowercase content digest.")
            shot["sha256"] = item["sha256"]
        normalized.append(shot)
        cursor += duration
        if cursor > maximum:
            raise ValueError("Production cut exceeds six hours.")
    if "runtime_frames" in raw and _integer(raw["runtime_frames"], "Plan runtime_frames", 1, maximum) != cursor:
        raise ValueError("Plan runtime_frames does not equal its ordered shot durations.")
    if "runtime_target_seconds" in raw and _seconds_frames(raw["runtime_target_seconds"], rate, "Plan runtime target") != cursor:
        raise ValueError("Plan runtime target does not equal its ordered shot durations.")
    plan.update(runtime_frames=cursor, shots=normalized)
    return plan


def _plan_hash(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _bindings(plan, value):
    if value is None:
        value = {}
    ids = {shot["id"] for shot in plan["shots"]}
    maximum = project_rate(plan).max_timeline_frames(21600)
    if not isinstance(value, dict) or set(value) - ids:
        raise ValueError("Production bindings must map only declared shot IDs to source selections.")
    result = {}
    for ident, item in value.items():
        if not isinstance(item, dict) or set(item) - {"asset_id", "in_frame", "allow_name_mismatch"}:
            raise ValueError("A shot binding supports asset_id, in_frame and allow_name_mismatch only.")
        asset_id = item.get("asset_id")
        if asset_id is not None:
            _identifier(asset_id, "Bound asset ID")
        alternate = item.get("allow_name_mismatch", False)
        if not isinstance(alternate, bool):
            raise ValueError("Alternate-take acknowledgement must be boolean.")
        result[ident] = {"asset_id": asset_id,
                         "in_frame": _integer(item.get("in_frame", 0), "Source in frame", 0, maximum),
                         "allow_name_mismatch": alternate}
    return result


def _review(plan, base, project_dir, bindings):
    assets = {asset["id"]: asset for asset in base["assets"]}
    rate, rows, errors, warnings, hashes = project_rate(plan), [], [], [], {}
    for shot in plan["shots"]:
        binding = bindings.get(shot["id"], {"asset_id": None, "in_frame": 0, "allow_name_mismatch": False})
        row = {**copy.deepcopy(shot), **copy.deepcopy(binding), "errors": [], "warnings": [],
               "out_frame": binding["in_frame"] + shot["duration_frames"], "available_frames": None, "sha256": None}
        asset = assets.get(binding["asset_id"])
        if asset is None:
            row["errors"].append("Select imported footage for " + shot["filename"] + ".")
        elif asset["kind"] != "video":
            row["errors"].append("This shot requires actual video; a still image, audio file or scene cannot replace it.")
        else:
            row["asset_name"] = asset["name"]
            row["source_width"], row["source_height"], row["source_fps"] = asset["width"], asset["height"], asset["fps"]
            available = math.floor(Fraction(str(asset["duration"])) * rate.fraction + Fraction(1, 2))
            try:
                source_rate = Fraction(str(asset.get("fps", "0/0")))
            except (ValueError, ZeroDivisionError):
                source_rate = Fraction(0)
            if source_rate == rate.fraction and type(asset.get("frames")) is int and asset["frames"] > 0:
                available = min(available, asset["frames"])
            row["available_frames"] = available
            row["head_handle_frames"] = binding["in_frame"]
            row["tail_handle_frames"] = available - row["out_frame"]
            if row["out_frame"] > available:
                row["errors"].append(f"Source ends at {available} plan frames; the selected range ends at {row['out_frame']}.")
            if asset["name"] != shot["filename"]:
                if not binding["allow_name_mismatch"]:
                    row["errors"].append("Source name differs from " + shot["filename"] + ". Confirm this alternate take explicitly.")
                else:
                    row["warnings"].append("Explicit alternate take: " + asset["name"] + ".")
            if (asset["width"], asset["height"]) != (plan["width"], plan["height"]):
                row["warnings"].append(f"Source {asset['width']} × {asset['height']} fits the {plan['width']} × {plan['height']} canvas; review scale and letterboxing.")
            if source_rate != rate.fraction:
                row["warnings"].append("Source cadence is conformed to the plan rate at normal speed; review moving footage.")
            if asset.get("color_transfer") in {"smpte2084", "arib-std-b67"}:
                row["errors"].append("Convert this HDR PQ/HLG take to the editor's SDR delivery space before conformance.")
            if asset["id"] not in hashes:
                hashes[asset["id"]] = _sha256(_media_path(project_dir, asset["path"]))
            row["sha256"] = hashes[asset["id"]]
            if asset.get("sha256") and asset["sha256"] != row["sha256"]:
                row["errors"].append("Imported footage has changed since admission. Import the intended take again before assembly.")
            if shot.get("sha256") and row["sha256"] != shot["sha256"]:
                row["errors"].append("Selected footage does not match the shot's required SHA-256 content identity.")
        row["ready"] = not row["errors"]
        errors.extend(shot["id"] + ": " + error for error in row["errors"])
        warnings.extend(shot["id"] + ": " + warning for warning in row["warnings"])
        rows.append(row)
    return {"plan": copy.deepcopy(plan), "plan_sha256": _plan_hash(plan), "bindings": copy.deepcopy(bindings),
            "shots": rows, "ready": not errors, "errors": errors, "warnings": warnings,
            "summary": {"shots": len(rows), "bound_shots": sum(row["ready"] for row in rows),
                        "frames": plan["runtime_frames"], "seconds": float(rate.seconds_for_frames(plan["runtime_frames"])),
                        "width": plan["width"], "height": plan["height"], "frame_rate": rate.as_dict()}}


def _inputs(document, project, project_dir, bindings):
    plan = normalize_plan(document)
    base = validate_project(project, project_dir)
    if not isinstance(base.get("settings", {}), dict):
        raise ValueError("Project settings must be an object.")
    return plan, base, _bindings(plan, bindings)


def review_plan(document, project, project_dir, bindings=None):
    """Inspect exact cut timings and selected real media without changing files."""
    plan, base, bound = _inputs(document, project, project_dir, bindings)
    return _review(plan, base, project_dir, bound)


def _record(review, stage):
    return {"version": 1, "plan": copy.deepcopy(review["plan"]), "plan_sha256": review["plan_sha256"],
            "bindings": copy.deepcopy(review["bindings"]), "last_action": stage, "issuance_effect": "NONE",
            "media_identities": {row["id"]: {"asset_id": row["asset_id"], "sha256": row["sha256"],
                                           "in_frame": row["in_frame"], "duration_frames": row["duration_frames"]}
                                 for row in review["shots"] if row["sha256"] is not None}}


def prepare_plan(document, project, project_dir, bindings=None):
    """Return a settings-only candidate; unresolved footage does not discard plans."""
    plan, candidate, bound = _inputs(document, project, project_dir, bindings)
    review = _review(plan, candidate, project_dir, bound)
    candidate.setdefault("settings", {})["production"] = _record(review, "plan_saved")
    return {**review, "project": candidate, "replace_timeline": False, "committed": False}


def conform_plan(document, project, project_dir, bindings=None, *, replace_format=False):
    """Return one complete editable cut; every shot must resolve to real footage."""
    if not isinstance(replace_format, bool):
        raise ValueError("replace_format must be boolean.")
    plan, candidate, bound = _inputs(document, project, project_dir, bindings)
    review = _review(plan, candidate, project_dir, bound)
    if not review["ready"]:
        raise ValueError("Production cut is incomplete. " + " ".join(review["errors"][:8]))
    if any(track.get("locked", False) for track in candidate["tracks"]):
        raise ValueError("Unlock the timeline tracks before replacing this edit with the planned cut.")
    same_format = (project_rate(candidate) == project_rate(plan)
                   and (candidate["width"], candidate["height"]) == (plan["width"], plan["height"]))
    if (candidate["clips"] or candidate["titles"]) and not same_format and not replace_format:
        raise ValueError("The existing edit has a different format. Explicitly confirm replacing its timeline and format.")
    candidate.update(name=plan["film"], width=plan["width"], height=plan["height"], fps=plan["fps"],
                     frame_rate=copy.deepcopy(plan["frame_rate"]), titles=[],
                     tracks=[{"id": 0, "name": "Production picture", "gain": 1, "mute": False, "solo": False, "locked": False}])
    candidate["clips"] = [{"id": "production_" + hashlib.sha256(row["id"].encode()).hexdigest()[:24],
                           "asset_id": row["asset_id"], "track": 0, "start": row["start_frame"],
                           "in": row["in_frame"], "duration": row["duration_frames"], "speed": 1, "reverse": False,
                           "production_shot_id": row["id"]} for row in review["shots"]]
    record = _record(review, "cut_assembled")
    # This is a receipt for the assembly operation, not a perpetual assertion
    # that subsequent timeline edits still conform. The user can review again.
    record["assembled_cut"] = [{key: clip[key] for key in ("id", "asset_id", "start", "in", "duration")}
                               for clip in candidate["clips"]]
    candidate.setdefault("settings", {})["production"] = record
    candidate = validate_project(candidate, project_dir)
    return {**review, "project": candidate, "replace_timeline": True, "committed": False,
            "warnings": review["warnings"] + ["The planned picture cut includes each source's embedded audio. Add sound design and review every shot before delivery."]}


def export_plan(project):
    """Return the portable shot requirements; assets and directories stay local."""
    settings = project.get("settings", {}) if isinstance(project, dict) else None
    record = settings.get("production") if isinstance(settings, dict) else None
    if not isinstance(record, dict) or not isinstance(record.get("plan"), dict):
        raise ValueError("Save or assemble a production plan before exporting its shot requirements.")
    plan = normalize_plan(record["plan"])
    return {"document": plan, "plan_sha256": _plan_hash(plan),
            "filename": re.sub(r"[^A-Za-z0-9_-]+", "_", plan["film"]).strip("_")[:100] + "-shot-plan.json",
            "warnings": ["This file contains shot requirements. Selected assets and source ranges remain in the saved CINEMATICUM project; media is not embedded."]}
