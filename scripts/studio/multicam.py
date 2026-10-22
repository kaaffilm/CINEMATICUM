"""Validated multicamera clocks, simultaneous-monitor plans and audio locks.

Audio locks select an existing synchronized camera; they do not bake a mix or
rewrite picture source fields. Every resolution keeps the clip's timeline gain,
pan, fades and retime, while selecting the locked camera's original PCM.
"""
from __future__ import annotations

import copy
import math
import re

if __package__:
    from .timebase import project_rate
else:
    from timebase import project_rate

HASH = re.compile(r"[a-f0-9]{64}\Z")


def binding(project, group, assets):
    """Explicit numeric binding survives JSON integer/float round trips."""
    angles = []
    for angle in group.get("angles", []):
        asset = assets.get(angle.get("asset_id"))
        if not asset or not HASH.fullmatch(str(asset.get("sha256", ""))):
            raise ValueError("Multicamera audio lock requires verified source media identities.")
        value = angle.get("in", 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Multicamera source clock is invalid.")
        angles.append({"id": angle["id"], "asset_id": asset["id"], "source_sha256": asset["sha256"], "in": value})
    return {"group_id": group["id"], "project_rate": project_rate(project).as_dict(), "angles": angles}


def group_for(project, clip):
    value = clip.get("multicam")
    if not isinstance(value, dict):
        return None, None
    group = next((g for g in project.get("multicam_groups", []) if g.get("id") == value.get("group_id")), None)
    angle = next((a for a in (group or {}).get("angles", []) if a.get("id") == value.get("angle_id")), None)
    if not group or not angle or angle.get("asset_id") != clip.get("asset_id"):
        raise ValueError("The multicamera clip has a stale or missing source binding.")
    return group, angle


def validate_lock(project, group, assets):
    value = group.get("audio_lock")
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"version", "angle_id", "stream_index", "channels", "clock"} or type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("Invalid multicamera audio-lock document.")
    expected = binding(project, group, assets)
    def no_boolean(item):
        if isinstance(item, bool):
            return False
        if isinstance(item, dict):
            return all(no_boolean(v) for v in item.values())
        if isinstance(item, list):
            return all(no_boolean(v) for v in item)
        return True
    if value["clock"] != expected or not no_boolean(value["clock"]):
        raise ValueError("The multicamera audio lock is stale after a source, synchronization or project-clock edit. Undo the edit; release the lock before changing the group clock.")
    angle = next((a for a in group["angles"] if a["id"] == value["angle_id"]), None)
    if not angle:
        raise ValueError("The locked sound camera is absent from its group.")
    asset = assets[angle["asset_id"]]
    index, channels = value["stream_index"], value["channels"]
    if type(index) is not int:
        raise ValueError("Choose an inspected integer audio stream for the locked camera.")
    stream = next((s for s in asset.get("audio_streams", []) if s.get("index") == index), None)
    if not asset.get("has_audio") or not stream:
        raise ValueError("The locked camera has no selected source audio stream.")
    if channels is not None and (not isinstance(channels, list) or len(channels) != 2 or any(type(v) is not int or not 0 <= v < stream["channels"] for v in channels)):
        raise ValueError("Map exactly two existing source channels from the locked camera.")
    return angle, asset, stream


def resolve_audio(project, clip, assets):
    """Return the effective sound clip/asset without mutating authored fields."""
    asset = assets[clip["asset_id"]]
    group, picture = group_for(project, clip)
    if not group or group.get("audio_lock") is None:
        return clip, asset
    sound, asset, stream = validate_lock(project, group, assets)
    value = group["audio_lock"]
    source_in = clip["in"] + sound["in"] - picture["in"]
    end = source_in + clip["duration"] * clip["speed"]
    rate = project_rate(project)
    limit = min(asset["duration"], stream["duration"]) * rate.fps
    if source_in < -1e-8 or end > limit + .5:
        raise ValueError("The edited multicamera clip extends beyond its locked audio source. Shorten the trim or choose another sound camera.")
    resolved = copy.deepcopy(clip)
    resolved["asset_id"], resolved["in"] = asset["id"], max(0, source_in)
    resolved["audio"].pop("stream_index", None); resolved["audio"].pop("channels", None)
    resolved["audio"]["stream_index"] = value["stream_index"]
    if value["channels"] is not None:
        resolved["audio"]["channels"] = list(value["channels"])
    return resolved, asset


def verify_sources(project, project_dir, group=None):
    """Refuse changed camera bytes before opening a monitor or exporting a lock."""
    if __package__:
        from .engine import _media_path
        from .media_management import _verified_bytes
    else:
        from engine import _media_path
        from media_management import _verified_bytes
    groups = [group] if group else [g for g in project.get("multicam_groups", []) if g.get("audio_lock")]
    assets = {a["id"]: a for a in project["assets"]}
    seen = set()
    for item in groups:
        binding(project, item, assets)
        for angle in item["angles"]:
            asset = assets[angle["asset_id"]]
            if asset["id"] in seen:
                continue
            seen.add(asset["id"])
            if not _verified_bytes(_media_path(project_dir, asset["path"]), asset["sha256"]):
                raise ValueError("A multicamera source changed after admission. Reimport and synchronize the camera again before monitor playback or export.")


def set_audio_lock(project, clip, values):
    group, picture = group_for(project, clip)
    if group is None:
        raise ValueError("Select a multicamera clip before locking its sound.")
    if set(values) - {"clip_id", "angle_id", "stream_index", "channels"}:
        raise ValueError("Audio lock accepts a camera, source stream and channel pair.")
    angle_id = values.get("angle_id")
    if angle_id is None:
        group.pop("audio_lock", None); return
    angle = next((a for a in group["angles"] if a["id"] == angle_id), None)
    if not angle:
        raise ValueError("Choose a sound camera from this multicamera group.")
    assets = {a["id"]: a for a in project["assets"]}; asset = assets[angle["asset_id"]]
    previous = group.get("audio_lock")
    defaults = previous if previous and previous["angle_id"] == angle_id else clip["audio"] if angle["id"] == picture["id"] else {}
    group["audio_lock"] = {"version": 1, "angle_id": angle_id,
        "stream_index": values.get("stream_index", defaults.get("stream_index", asset.get("audio_stream_index"))),
        "channels": copy.deepcopy(values.get("channels", defaults.get("channels"))), "clock": binding(project, group, assets)}
    validate_lock(project, group, assets)


def monitor_plan(project, clip, frame):
    group, selected = group_for(project, clip)
    if group is None:
        raise ValueError("Select a multicamera clip to open its simultaneous monitor.")
    if isinstance(frame, bool) or not isinstance(frame, (int, float)) or not math.isfinite(frame) or not clip["start"] <= frame < clip["start"] + clip["duration"]:
        raise ValueError("The monitor playhead must be inside the selected multicamera clip.")
    assets = {a["id"]: a for a in project["assets"]}; rate = project_rate(project)
    common_in = clip["in"] - selected["in"]
    local = min(clip["duration"] - 1, frame - clip["start"])
    offset = common_in + (clip["duration"] - 1 - local if clip["reverse"] else local) * clip["speed"]
    angles = []
    for angle in group["angles"]:
        asset = assets[angle["asset_id"]]; source_frame = angle["in"] + offset
        available = source_frame >= 0 and source_frame < asset["duration"] * rate.fps
        angles.append({"id": angle["id"], "asset_id": asset["id"], "name": asset["name"], "source_frame": source_frame,
                       "source_in": angle["in"], "available": available, "source_sha256": asset.get("sha256"),
                       "duration": asset["duration"], "width": asset["width"], "height": asset["height"],
                       "url": f"/api/projects/{project['id']}/media/{asset['id']}"})
    return {"project_id": project["id"], "clip_id": clip["id"], "group_id": group["id"], "name": group["name"],
            "fps": rate.fps, "frame": frame, "clip_start": clip["start"], "clip_duration": clip["duration"], "group_in": common_in,
            "selected_angle": selected["id"], "audio_lock": copy.deepcopy(group.get("audio_lock")), "angles": angles,
            "cuttable": clip["speed"] == 1 and not clip["reverse"] and not clip.get("tracking") and not clip.get("compositor")}
