"""Bounded OpenTimelineIO JSON interchange for real cut timelines.

Only Timeline/Stack/Track/Clip/Gap and ExternalReference are interpreted. No
external URL is opened, no media linker or schema plugin is executed, and an
import returns an unsaved candidate. Rich CINEMATICUM authoring data travels in
namespaced metadata; other applications receive cuts, gaps and media references,
not a promise that proprietary effects translate.

Schema audited at OpenTimelineIO f8a2f36df61ce88eb6b73a57df393a87d3e3e42e:
docs/tutorials/otio-serialized-schema-only-fields.md and src/opentimelineio/clip.cpp.
Produced documents are also tested with the official OpenTimelineIO 0.18.1 reader.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
from collections import OrderedDict
import threading

if __package__:
    from .compositor import MAX_NODES
    from .editorial import sequence_duration
    from .engine import _media_path, validate_project, track_state
    from .scene import validate_scene
    from .timebase import parse_rate, project_rate
else:
    from compositor import MAX_NODES
    from editorial import sequence_duration
    from engine import _media_path, validate_project, track_state
    from scene import validate_scene
    from timebase import parse_rate, project_rate


MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
_HASHES = OrderedDict()
_HASH_LOCK = threading.Lock()
_TIME_EFFECTS = {"TimeEffect.1", "LinearTimeWarp.1", "FreezeFrame.1"}


def _json_copy(value):
    """Bound untrusted structure before any media lookup or project mutation."""
    def reject_constant(value):
        raise ValueError("OTIO must contain finite JSON numbers.")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON member in OTIO: " + key[:80])
            result[key] = value
        return result

    try:
        if isinstance(value, (str, bytes)):
            if len(value if isinstance(value, bytes) else value.encode("utf-8")) > MAX_DOCUMENT_BYTES:
                raise ValueError("OTIO exceeds the 8 MiB import limit.")
            result = json.loads(value, parse_constant=reject_constant, object_pairs_hook=unique)
        else:
            encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
            if len(encoded.encode("utf-8")) > MAX_DOCUMENT_BYTES:
                raise ValueError("OTIO exceeds the 8 MiB import limit.")
            result = json.loads(encoded)
    except (TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid OTIO JSON document.") from exc
    pending, count = [(result, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if depth > 48 or count > 300000:
            raise ValueError("OTIO structure exceeds the bounded import limit.")
        if isinstance(node, dict):
            pending.extend((item, depth + 1) for item in node.values())
        elif isinstance(node, list):
            pending.extend((item, depth + 1) for item in node)
        elif isinstance(node, float) and not math.isfinite(node):
            raise ValueError("OTIO must contain finite JSON numbers.")
    return result


def _sha256(path):
    path = Path(path)
    before = path.stat()
    key = (str(path), before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_ino)
    with _HASH_LOCK:
        cached = _HASHES.get(key)
        if cached:
            _HASHES.move_to_end(key)
            return cached
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino):
        raise ValueError("Media changed while computing its interchange identity; retry after the write finishes.")
    value = digest.hexdigest()
    with _HASH_LOCK:
        _HASHES[key] = value
        while len(_HASHES) > 512:
            _HASHES.popitem(last=False)
    return value


def _rt(value, rate):
    return {"OTIO_SCHEMA": "RationalTime.1", "value": value, "rate": rate.fps}


def _range(start, duration, rate):
    return {"OTIO_SCHEMA": "TimeRange.1", "start_time": _rt(start, rate), "duration": _rt(duration, rate)}


def _item(schema, name="", **fields):
    return {"OTIO_SCHEMA": schema, "name": name, "metadata": {}, "source_range": None,
            "effects": [], "markers": [], "enabled": True, "color": None, **fields}


def _public_digest(document):
    # A change detector, not an authenticity signature. Metadata is independently
    # validated; the digest only prevents stale private snapshots from silently
    # replacing edits another application made to the public OTIO structure.
    def clean(value):
        if isinstance(value, dict):
            result = {key: clean(item) for key, item in value.items() if key != "metadata"}
            if result.get("OTIO_SCHEMA") == "Clip.1":
                result["OTIO_SCHEMA"] = "Clip.2"
                result["media_references"] = {"DEFAULT_MEDIA": result.pop("media_reference", None)}
                result["active_media_reference_key"] = "DEFAULT_MEDIA"
            return result
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    return hashlib.sha256(json.dumps(clean(document), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _validated_project(project, project_dir):
    """Validate private authoring data before export or candidate application."""
    normalized = validate_project(project, project_dir)
    settings = normalized.setdefault("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("Project settings must be an object.")
    if settings.get("scene") is not None:
        settings["scene"] = validate_scene(settings["scene"], width=normalized["width"], height=normalized["height"])
    return normalized


def _asset_reference_slots(project):
    """Yield all editable media-reference objects, including dormant graph nodes.

    A compositor's media_source is a dependency even if it is disconnected from
    the current output: dropping its identity would corrupt a later graph edit.
    Enumerate only the supported schema slots, never arbitrary asset_id-looking
    metadata (which may describe historical provenance rather than dependencies).
    Import calls this before destination validation, while the references still
    carry source-project IDs, so malformed structures must fail here explicitly.
    """
    stored = project.get("sequences", [])
    if not isinstance(stored, list) or len(stored) >= 64:
        raise ValueError("Invalid CINEMATICUM sequence library in OTIO authoring metadata.")
    for sequence in stored:
        if not isinstance(sequence, dict) or "sequences" in sequence:
            raise ValueError("Invalid CINEMATICUM stored sequence.")
        yield from _asset_reference_slots(sequence)
    groups = project.get("multicam_groups", [])
    if not isinstance(groups, list) or len(groups) > 64:
        raise ValueError("Invalid multicamera group inventory.")
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("angles"), list) or len(group["angles"]) > 16:
            raise ValueError("Invalid multicamera source angles.")
        for angle in group["angles"]:
            if not isinstance(angle, dict):
                raise ValueError("Invalid multicamera source angle.")
            yield angle
    for key, limit in (("clips", 256), ("titles", 128)):
        items = project.get(key, [])
        if not isinstance(items, list) or len(items) > limit:
            raise ValueError("Invalid CINEMATICUM " + key + " in OTIO authoring metadata.")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid CINEMATICUM media reference in OTIO authoring metadata.")
            if (key == "clips" and item.get("sequence_id") is None) or item.get("asset_id") is not None:
                yield item
            graph = item.get("compositor") if key == "clips" else None
            if graph is None:
                continue
            if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or len(graph["nodes"]) > MAX_NODES:
                raise ValueError("Invalid CINEMATICUM compositor in OTIO authoring metadata.")
            for node in graph["nodes"]:
                if not isinstance(node, dict):
                    raise ValueError("Invalid CINEMATICUM compositor node in OTIO authoring metadata.")
                if node.get("type") == "media_source":
                    if not isinstance(node.get("params"), dict):
                        raise ValueError("Invalid CINEMATICUM compositor media source in OTIO authoring metadata.")
                    yield node["params"]


def _asset_identities(value):
    """Validate the private identity table before resolving any private media."""
    if (not isinstance(value, dict) or len(value) > 512
            or any(not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", ident)
                   or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                   for ident, digest in value.items())):
        raise ValueError("CINEMATICUM OTIO asset_sha256 must map source asset IDs to valid SHA-256 identities.")
    return value


def export_otio(project, project_dir):
    """Return {document, warnings}; media remains in the existing project."""
    p = _validated_project(project, project_dir)
    if any("audio_mixer" in sequence for sequence in [p]+p.get("sequences",[])):
        raise ValueError("OTIO public audio tracks do not encode CINEMATICUM buses, sends or master loudness. Render the mix to a new source before exchanging it.")
    if any(clip.get("retime") for sequence in [p] + p.get("sequences", []) for clip in sequence.get("clips", [])):
        raise ValueError("OTIO does not preserve CINEMATICUM's variable-speed and optical-flow recipe. Render and reimport those edits before exchanging them.")
    if __package__:
        from .otio_compositions import needs_export, export_compositions
    else:
        from otio_compositions import needs_export, export_compositions
    if needs_export(p):
        return export_compositions(p, project_dir)
    if any(clip.get("sequence_id") for clip in p["clips"]):
        if __package__:
            from .sequence_interchange import export_nested
        else:
            from sequence_interchange import export_nested
        return export_nested(p, project_dir)
    rate = project_rate(p)
    assets = {asset["id"]: asset for asset in p["assets"]}
    used = {reference["asset_id"] for reference in _asset_reference_slots(p)}
    identities = {ident: _sha256(_media_path(project_dir, assets[ident]["path"])) for ident in sorted(used)}
    warnings = ["OTIO exchanges cuts, gaps and references. Relink the project-relative media paths in other editors; media is not embedded."]
    if p["titles"]:
        warnings.append("Titles are retained only in CINEMATICUM metadata; other editors will not display them from this OTIO file.")
    if any(c.get("compositor") or c.get("tracking") or c.get("color_pipeline") or c["keyframes"] or c["grade"] != {"exposure": 0, "contrast": 1, "saturation": 1, "temperature": 0}
           or any(c[key] != value for key, value in (("x", 0), ("y", 0), ("scale", 1), ("rotation", 0), ("opacity", 1), ("volume", 1)))
           or any(c["effects"].values()) or c["audio"]["fade_in"] or c["audio"]["fade_out"] or c["audio"]["pan"] for c in p["clips"]):
        warnings.append("Transforms, effects, color, tracking, titles and audio automation remain private CINEMATICUM metadata; other editors receive the unprocessed cuts.")
    if any(c.get("color_pipeline", {}).get("lut") for c in p["clips"] if isinstance(c.get("color_pipeline"), dict)):
        warnings.append("LUT tables are project-owned files and are not embedded in OTIO. Import the same LUTs into a destination CINEMATICUM project before restoring private authoring data.")
    if any(t["gain"] != 1 or t["solo"] for t in p["tracks"]):
        warnings.append("Track gain and solo relationships remain private metadata; public track enable flags reflect the current mixer state.")
    if any(c["speed"] != 1 or c["reverse"] for c in p["clips"]):
        raise ValueError("OTIO cut export does not support speed changes or reverse. Render those shots first or export the CINEMATICUM project.")
    tracks = []
    full_duration = sequence_duration(p)

    def make_track(track_id, clips, companion=False):
        settings = next((t for t in p["tracks"] if t["id"] == track_id), {})
        name = settings.get("name", ("A" + str(-track_id)) if track_id < 0 else ("V" + str(track_id + 1)))
        track = _item("Track.1", name + (" source audio" if companion else ""),
                      kind="Audio" if companion or track_id < 0 else "Video", children=[],
                      enabled=track_state(p, track_id)[0])
        track["metadata"] = {"cinematicum": {"track_id": track_id, "role": "embedded_audio" if companion else "native"}}
        cursor = 0
        for clip in sorted(clips, key=lambda c: (c["start"], c["id"])):
            if clip["start"] < cursor:
                raise ValueError("Overlapping clips on the same track cannot be represented by this OTIO cut export. Move them to separate tracks first.")
            if clip["start"] > cursor:
                track["children"].append(_item("Gap.1", source_range=_range(0, clip["start"] - cursor, rate)))
            asset = assets[clip["asset_id"]]
            reference = {"OTIO_SCHEMA": "ExternalReference.1", "name": asset["name"],
                         "metadata": {"cinematicum": {"sha256": identities[asset["id"]], "asset_id": asset["id"]}},
                         "available_range": None if asset["kind"] == "image" else _range(0, asset["duration"] * rate.fps, rate),
                         "available_image_bounds": None, "target_url": asset["path"]}
            item = _item("Clip.2", asset["name"], source_range=_range(clip["in"], clip["duration"], rate),
                         media_references={"DEFAULT_MEDIA": reference}, active_media_reference_key="DEFAULT_MEDIA")
            item["metadata"] = {"cinematicum": {"clip_id": clip["id"], "role": "embedded_audio" if companion else "native"}}
            track["children"].append(item)
            cursor = clip["start"] + clip["duration"]
        if cursor < full_duration:
            track["children"].append(_item("Gap.1", source_range=_range(0, full_duration - cursor, rate)))
        return track

    ids = sorted({c["track"] for c in p["clips"]} | {t["id"] for t in p["tracks"]}, key=lambda i: (i < 0, i if i >= 0 else -i))
    for track_id in ids:
        clips = [c for c in p["clips"] if c["track"] == track_id]
        tracks.append(make_track(track_id, clips))
        if track_id >= 0:
            audio_clips = [c for c in clips if assets[c["asset_id"]]["has_audio"]]
            if audio_clips:
                tracks.append(make_track(track_id, audio_clips, companion=True))
    if not tracks and full_duration:
        tracks.append(make_track(0, []))
    if sum(t["kind"] == "Video" for t in tracks) > 1:
        warnings.append("Video track stacking is retained, but blend/compositing behavior in other editors may differ.")
    document = {"OTIO_SCHEMA": "Timeline.1", "name": p["name"], "metadata": {},
                "global_start_time": _rt(0, rate), "tracks": _item("Stack.1", "tracks", children=tracks)}
    # The snapshot is restored only when the public tree still has exactly the
    # recorded timing/reference/track representation. Its paths are never used
    # for media admission: every referenced identity must resolve locally.
    snapshot = copy.deepcopy(p)
    snapshot.pop("assets")
    document["metadata"] = {"cinematicum": {"version": 1, "frame_rate": rate.as_dict(),
                                              "project": snapshot, "asset_sha256": identities,
                                              "public_sha256": _public_digest(document)}}
    return {"document": _json_copy(document), "warnings": warnings}


def _object(value, schemas, label):
    if not isinstance(value, dict) or value.get("OTIO_SCHEMA") not in schemas:
        raise ValueError(f"Unsupported {label}; expected {', '.join(sorted(schemas))}.")
    return value


def _metadata(node):
    value = node.get("metadata", {})
    if not isinstance(value, dict):
        raise ValueError("OTIO metadata must be an object.")
    own = value.get("cinematicum", {})
    if not isinstance(own, dict):
        raise ValueError("CINEMATICUM OTIO metadata must be an object.")
    return own


def _time_frames(value, rate, label):
    _object(value, {"RationalTime.1"}, label)
    number, clock = value.get("value"), value.get("rate")
    if (isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or abs(number) > 10**12
            or isinstance(clock, bool) or not isinstance(clock, (int, float)) or not math.isfinite(clock) or not 0 < clock <= 10**9):
        raise ValueError(f"{label} must have a bounded finite value and positive rate.")
    if abs(clock - rate.fps) < 1e-9:
        source_rate = rate.fraction
    else:
        try:
            source_rate = parse_rate(clock, maximum=240).fraction
        except ValueError:
            source_rate = Fraction(str(clock))
    return Fraction(str(number)) * rate.fraction / source_rate


def _time_range(value, rate, label):
    _object(value, {"TimeRange.1"}, label)
    return (_time_frames(value.get("start_time"), rate, label + " start"),
            _time_frames(value.get("duration"), rate, label + " duration"))


def _integer_frame(value, label):
    nearest = round(value)
    if abs(value - nearest) > Fraction(1, 1000000):
        raise ValueError(f"{label} falls between project frames; this cut importer will not silently round it.")
    return nearest


def _noneditorial(node, label, warnings):
    if not isinstance(node.get("enabled", True), bool):
        raise ValueError(f"{label} enabled must be boolean.")
    effects, markers = node.get("effects", []), node.get("markers", [])
    if not isinstance(effects, list) or not isinstance(markers, list) or len(effects) > 256 or len(markers) > 4096:
        raise ValueError(f"{label} has invalid or excessive effects/markers.")
    for effect in effects:
        if not isinstance(effect, dict):
            raise ValueError("Invalid OTIO effect.")
        if effect.get("OTIO_SCHEMA") in _TIME_EFFECTS or effect.get("effect_name") in {"LinearTimeWarp", "FreezeFrame", "TimeWarp"}:
            raise ValueError("OTIO timewarp and freeze-frame effects are not supported by this cut importer.")
        warnings.append(f"{label}: effect {str(effect.get('name') or effect.get('effect_name') or effect.get('OTIO_SCHEMA'))[:100]} is not applied.")
    if markers:
        warnings.append(f"{label}: {len(markers)} OTIO markers are not imported into this timeline.")


def import_otio(document, project, project_dir, asset_map=None):
    """Return {project, warnings}; never open OTIO paths or save the candidate.

    asset_map maps exact target_url strings (or 'sha256:<digest>') to an already
    imported asset_id. Otherwise actual local file hashes must match the document.
    """
    try:
        return _import_otio(document, project, project_dir, asset_map)
    except (TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ValueError("Malformed or inconsistent OTIO document.") from exc


def _import_otio(document, project, project_dir, asset_map):
    doc = _json_copy(document)
    _object(doc, {"Timeline.1"}, "top-level OTIO object")
    if __package__:
        from .otio_compositions import needs_import, import_compositions
    else:
        from otio_compositions import needs_import, import_compositions
    if needs_import(doc):
        return import_compositions(doc, project, project_dir, asset_map)
    if __package__:
        from .sequence_interchange import has_nested, import_nested
    else:
        from sequence_interchange import has_nested, import_nested
    if has_nested(doc) or _metadata(doc).get("nested_sequences") == 1:
        return import_nested(doc, project, project_dir, asset_map)
    base = _validated_project(project, project_dir)
    assets = {a["id"]: a for a in base["assets"]}
    mapping = {} if asset_map is None else asset_map
    if not isinstance(mapping, dict) or len(mapping) > 512 or any(not isinstance(k, str) or len(k) > 4096 or not isinstance(v, str) or v not in assets for k, v in mapping.items()):
        raise ValueError("OTIO asset mappings must point to already-imported asset IDs.")
    own = _metadata(doc)
    if own and own.get("version") != 1:
        raise ValueError("Unsupported CINEMATICUM OTIO metadata version.")
    warnings = []
    if own.get("frame_rate") is not None:
        rate = parse_rate(own["frame_rate"])
    elif doc.get("global_start_time") is not None:
        rate = parse_rate(doc["global_start_time"].get("rate"))
    else:
        rate = project_rate(base)
        warnings.append("The OTIO has no project clock; cut times are conformed to the destination project's frame rate.")
    global_start = doc.get("global_start_time")
    if global_start is not None and _time_frames(global_start, rate, "Timeline start") != 0:
        warnings.append("The source global timecode is retained in import metadata; CINEMATICUM's editable timeline starts at frame zero.")
    stack = _object(doc.get("tracks"), {"Stack.1"}, "timeline tracks")
    _noneditorial(stack, "Timeline", warnings)
    if stack.get("source_range") is not None or not stack.get("enabled", True):
        raise ValueError("Trimmed or disabled OTIO timeline stacks are not supported.")
    tracks = stack.get("children")
    if not isinstance(tracks, list) or len(tracks) > 48:
        raise ValueError("OTIO must contain at most 48 simple tracks.")
    resolved, hashes = {}, {}

    def asset_for(reference):
        _object(reference, {"ExternalReference.1"}, "media reference")
        target = reference.get("target_url")
        if not isinstance(target, str) or not target or len(target) > 4096 or "\x00" in target:
            raise ValueError("OTIO external reference needs a bounded target_url string.")
        meta = _metadata(reference)
        digest = meta.get("sha256")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("OTIO media SHA-256 is invalid.")
        if meta.get("asset_id") is not None and not isinstance(meta["asset_id"], str):
            raise ValueError("OTIO source asset identity must be a string.")
        cache_key = (target, digest, meta.get("asset_id"))
        if cache_key in resolved:
            return resolved[cache_key]
        selected = mapping.get(target) or (mapping.get("sha256:" + digest) if digest else None)
        if selected is None and digest:
            preferred = meta.get("asset_id")
            order = ([preferred] if preferred in assets else []) + [key for key in assets if key != preferred]
            for ident in order:
                if ident not in hashes:
                    hashes[ident] = _sha256(_media_path(project_dir, assets[ident]["path"]))
                if hashes[ident] == digest:
                    selected = ident
                    break
        if selected is None:
            raise ValueError("Unresolved OTIO media: " + target[:160] + ". Import the media first and provide an explicit existing-asset mapping.")
        if digest and (mapping.get(target) or mapping.get("sha256:" + digest)):
            actual = hashes.setdefault(selected, _sha256(_media_path(project_dir, assets[selected]["path"])))
            if actual != digest:
                warnings.append("Explicit relink uses different media content for " + target[:160] + ".")
        resolved[cache_key] = selected
        return selected

    public_clips, track_settings = [], []
    video_index, audio_index, event_count, public_duration = 0, 0, 0, 0
    for index, track in enumerate(tracks):
        _object(track, {"Track.1"}, "track (nested stacks/transitions are unsupported)")
        _noneditorial(track, f"Track {index+1}", warnings)
        if track.get("source_range") is not None:
            raise ValueError("Trimmed OTIO tracks require nesting/conform support and are not silently flattened.")
        kind = track.get("kind")
        if kind not in {"Video", "Audio"}:
            raise ValueError("OTIO track kind must be Video or Audio.")
        if kind == "Video":
            track_id, video_index = video_index, video_index + 1
        else:
            track_id, audio_index = -audio_index - 1, audio_index + 1
        private_track = _metadata(track)
        children = track.get("children")
        if not isinstance(children, list) or len(children) > 512:
            raise ValueError("OTIO tracks must contain at most 512 clips/gaps.")
        cursor = 0
        track_settings.append({"id": track_id, "name": str(track.get("name") or f"Track {index+1}")[:100],
                               "mute": not track.get("enabled", True), "solo": False, "locked": False, "gain": 1})
        for item in children:
            event_count += 1
            if event_count > 1024:
                raise ValueError("OTIO exceeds the 1,024-event import limit.")
            _object(item, {"Clip.1", "Clip.2", "Gap.1"}, "track item (transitions and nested sequences are unsupported)")
            _noneditorial(item, f"Item {event_count}", warnings)
            start_time, duration_value = _time_range(item.get("source_range"), rate, "Item source range")
            duration = _integer_frame(duration_value, "Clip/gap duration")
            if not 1 <= duration <= rate.max_timeline_frames(21600) or cursor + duration > rate.max_timeline_frames(21600):
                raise ValueError("OTIO cut/gap duration exceeds the six-hour timeline bound.")
            if item["OTIO_SCHEMA"] == "Gap.1":
                cursor += duration
                continue
            if not item.get("enabled", True):
                raise ValueError("Disabled OTIO clips are not supported; disable the track instead.")
            if item["OTIO_SCHEMA"] == "Clip.1":
                reference = item.get("media_reference")
            else:
                references = item.get("media_references")
                active = item.get("active_media_reference_key")
                if not isinstance(references, dict) or not isinstance(active, str) or active not in references:
                    raise ValueError("OTIO clip has no valid active media reference.")
                reference = references[active]
            asset_id = asset_for(reference)
            available_start = Fraction(0)
            if reference.get("available_range") is not None:
                available_start, available_duration = _time_range(reference["available_range"], rate, "Media available range")
                if available_duration < 0 or start_time < available_start or start_time + duration_value > available_start + available_duration + Fraction(1, 2):
                    raise ValueError("OTIO clip extends outside its declared available media range.")
            source_in = start_time - available_start
            if source_in < 0:
                raise ValueError("OTIO source in cannot precede the available media.")
            private_clip = _metadata(item)
            public_clips.append({"id": f"otio_clip_{len(public_clips)+1}", "asset_id": asset_id,
                                 "track": track_id, "start": cursor, "in": float(source_in), "duration": duration,
                                 "volume": 0 if kind == "Video" else 1,
                                 "_private": private_clip, "_track_private": private_track, "_kind": kind})
            cursor += duration
        public_duration = max(public_duration, cursor)
    # Exact unedited self-roundtrip: use private authoring data only after every
    # public reference was resolved and the public document was validated above.
    if own and own.get("public_sha256") == _public_digest(doc):
        snapshot = own.get("project")
        if not isinstance(snapshot, dict):
            raise ValueError("Missing CINEMATICUM authoring snapshot.")
        candidate = copy.deepcopy(snapshot)
        candidate["id"], candidate["assets"] = base["id"], copy.deepcopy(base["assets"])
        native = [c for c in public_clips if c["_private"].get("role") != "embedded_audio"]
        saved_clips = candidate.get("clips")
        if not isinstance(saved_clips, list) or len(saved_clips) != len(native):
            raise ValueError("CINEMATICUM metadata does not match the public OTIO cut list.")
        if sequence_duration(candidate) != public_duration:
            raise ValueError("Private CINEMATICUM timing: sequence duration conflicts with public OTIO timing.")
        identities = _asset_identities(own.get("asset_sha256"))
        references = list(_asset_reference_slots(candidate))
        for reference in references:
            source_id = reference.get("asset_id")
            if not isinstance(source_id, str) or source_id not in identities:
                # Older exports omitted graph-only dependencies. Even in the
                # original project, a matching ID cannot establish that the
                # media bytes are still the same. Re-export with a full table.
                raise ValueError("A private CINEMATICUM media reference has no verified SHA-256 identity. "
                                 "Re-export the OTIO from its source project with complete media dependencies.")

        def verify_private_media(source_id, destination_id):
            if destination_id not in hashes:
                hashes[destination_id] = _sha256(_media_path(project_dir, assets[destination_id]["path"]))
            if hashes[destination_id] != identities[source_id]:
                raise ValueError("Private CINEMATICUM media identity mismatch for " + source_id
                                 + ". Restoring authoring data requires byte-identical imported media.")

        public_by_id = {}
        for clip in native:
            ident = clip["_private"].get("clip_id")
            if not isinstance(ident, str) or ident in public_by_id:
                raise ValueError("Ambiguous CINEMATICUM clip identity in OTIO.")
            public_by_id[ident] = clip
        asset_remap = {}
        for saved in saved_clips:
            public = public_by_id.get(saved.get("id"))
            if (not public or saved.get("start") != public["start"] or saved.get("duration") != public["duration"]
                    or abs(float(saved.get("in", 0)) - public["in"]) > 1e-6 or saved.get("speed", 1) != 1 or saved.get("reverse", False)):
                raise ValueError("Private CINEMATICUM timing conflicts with public OTIO timing.")
            if saved.get("track") != public["_track_private"].get("track_id") or (saved["track"] < 0) != (public["_kind"] == "Audio"):
                raise ValueError("Private CINEMATICUM track identity conflicts with the public OTIO track.")
            verify_private_media(saved["asset_id"], public["asset_id"])
            asset_remap.setdefault(saved["asset_id"], public["asset_id"])
        companions = {}
        for clip in public_clips:
            if clip["_private"].get("role") != "embedded_audio":
                continue
            ident = clip["_private"].get("clip_id")
            native_clip = public_by_id.get(ident)
            if (ident in companions or not native_clip or native_clip["_kind"] != "Video" or clip["_kind"] != "Audio"
                    or any(clip[field] != native_clip[field] for field in ("asset_id", "start", "in", "duration"))
                    or clip["_track_private"].get("track_id") != native_clip["_track_private"].get("track_id")):
                raise ValueError("Linked source audio no longer matches its CINEMATICUM picture clip.")
            companions[ident] = clip
        for ident, clip in public_by_id.items():
            if clip["_kind"] == "Video" and assets[clip["asset_id"]]["has_audio"] and ident not in companions:
                raise ValueError("A CINEMATICUM picture clip is missing its linked source-audio track.")
        for source_id, digest in identities.items():
            if source_id in asset_remap:
                continue
            dummy = {"OTIO_SCHEMA": "ExternalReference.1", "target_url": "sha256:" + str(digest),
                     "metadata": {"cinematicum": {"asset_id": source_id, "sha256": digest}}}
            asset_remap[source_id] = asset_for(dummy)
            verify_private_media(source_id, asset_remap[source_id])
        # Remap all references only after the complete dependency set has been
        # resolved and content-verified. Source IDs never fall through to an
        # unrelated destination asset with the same ID.
        for reference in references:
            reference["asset_id"] = asset_remap[reference["asset_id"]]
        candidate["frame_rate"], candidate["fps"] = rate.as_dict(), rate.fps
        warnings.append("CINEMATICUM authoring metadata restored, including effects and mixer state. No project has been saved.")
    else:
        if len(public_clips) > 256 or video_index > 16 or audio_index > 16:
            raise ValueError("This timeline exceeds CINEMATICUM's 256-clip or 16 video/16 audio track limits.")
        candidate = copy.deepcopy(base)
        if base.get("sequences") and project_rate(base) != rate:
            raise ValueError("Other sequences use this project clock. Import a differently formatted OTIO into a new project.")
        candidate.update(name=str(doc.get("name") or "Imported OTIO")[:200], fps=rate.fps, frame_rate=rate.as_dict(),
                         clips=[{k: v for k, v in c.items() if not k.startswith("_")} for c in public_clips],
                         tracks=track_settings, titles=[], captions=[], sequence_duration=public_duration)
        candidate.pop("caption_style", None)
        if rate.fraction not in (Fraction(30000,1001), Fraction(60000,1001)):
            candidate.setdefault("settings", {}).pop("timecode_mode", None)
        if own:
            warnings.append("The public OTIO was edited externally; stale CINEMATICUM effects/titles/mixer metadata was not applied. Review the imported cuts before replacing the timeline.")
        if video_index > 1:
            warnings.append("Video tracks retain stack order. Unsupported blend/transition semantics are not reconstructed.")
        if any(assets[c["asset_id"]]["has_audio"] for c in public_clips if c["_kind"] == "Video"):
            warnings.append("Video-track items import picture only; sound must be represented on OTIO Audio tracks to avoid duplicated audio.")
        if global_start is not None:
            candidate.setdefault("settings", {})["otio_global_start_time"] = copy.deepcopy(global_start)
    return {"project": _validated_project(candidate, project_dir), "warnings": list(dict.fromkeys(warnings))}
