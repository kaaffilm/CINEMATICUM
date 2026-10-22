"""Application jobs and owned application plans for checkpoint-backed tracking."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import shutil
import tempfile


def track(store, project_id, payload):
    from learned_tracking import ARTIFACT_NAMES, run_learned_tracking, validate_request
    from studio_tools import _owned_artifact
    if not isinstance(payload, dict) or set(payload) - {"project", "clip_id", "recipe"} or not {"clip_id", "recipe"} <= set(payload):
        raise ValueError("Learned inference requires a clip and one explicit recipe.")
    project = store.analysis_snapshot(project_id, payload)
    directory = store.project_dir(project_id)
    clip_id = payload["clip_id"]
    recipe = validate_request(project, directory, clip_id, copy.deepcopy(payload["recipe"]))

    def work(job_id, progress, event):
        output = directory / "learned" / "outputs" / job_id
        result = run_learned_tracking(project, directory, clip_id, recipe, output,
                                     progress=progress, cancel_event=event)
        if event.is_set():
            raise RuntimeError("Learned tracking cancelled")
        base = f"/api/projects/{project_id}/learned/outputs/{job_id}/"
        result["artifact_urls"] = {name: base + name for name in sorted(ARTIFACT_NAMES) if (output / name).is_file()}
        result["display_url"] = base + "preview.png"
        result["receipt_url"] = base + "receipt.json"
        if result.get("mask_path"):
            source = _owned_artifact(directory, result["mask_path"])
            with tempfile.TemporaryDirectory(prefix="learned-admit-", dir=directory) as temporary:
                mask = Path(temporary) / "mask.mkv"
                shutil.copyfile(source, mask)
                if event.is_set():
                    raise RuntimeError("Learned tracking cancelled")
                asset = store.admit(project_id, mask, "SAM 2 matte " + job_id[:8] + ".mkv", result["provenance"])
            result["asset"] = asset
            result["url"] = f"/api/projects/{project_id}/media/{asset['id']}"
        return result

    return store.submit(project_id, "learned-tracking", work,
                        {"project": project, "clip_id": clip_id, "recipe": recipe})


def apply_plan(store, project_id, payload):
    from learned_tracking import mask_application, point_application
    from studio_tools import artifact
    allowed = {"project", "clip_id", "job_id", "action", "invert", "hold_still", "point_id", "corrections", "frame_start", "frame_count"}
    if (not isinstance(payload, dict) or set(payload) - allowed
            or not {"project", "clip_id", "job_id", "action"} <= set(payload)
            or not isinstance(payload["job_id"], str) or not re.fullmatch(r"[a-f0-9]{32}", payload["job_id"])):
        raise ValueError("Apply a measured result from one owned learned job.")
    project = store.analysis_snapshot(project_id, payload)
    directory = store.project_dir(project_id)
    result_path = artifact(store, project_id, "learned", payload["job_id"], "result.json")
    if result_path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("The learned result exceeds its metadata bound.")
    result = json.loads(result_path.read_text())
    if result.get("output_id") != payload["job_id"]:
        raise ValueError("The learned result does not match this owned job.")
    if payload["action"] == "mask":
        if set(payload) - {"project", "clip_id", "job_id", "action", "invert", "hold_still"}:
            raise ValueError("A mask application accepts only its inversion option.")
        mask = next((asset for asset in project["assets"]
                     if asset.get("provenance", {}).get("type") == "cinematicum-learned-mask"
                     and asset["provenance"].get("output_id") == payload["job_id"]
                     and asset.get("sha256") == result.get("mask_sha256")), None)
        if mask is None:
            raise ValueError("The measured matte has not been admitted into this project.")
        plan = mask_application(project, directory, payload["clip_id"], result, mask, invert=payload.get("invert", False),
                                hold_still=payload.get("hold_still", False))
    elif payload["action"] == "point":
        if "invert" in payload or "hold_still" in payload or "point_id" not in payload:
            raise ValueError("A point application needs one measured point identity.")
        plan = point_application(project, directory, payload["clip_id"], result, payload["point_id"],
                                 corrections=payload.get("corrections"), frame_start=payload.get("frame_start"),
                                 frame_count=payload.get("frame_count"))
    else:
        raise ValueError("Choose mask or point application.")
    return {"clip_id": payload["clip_id"], "recipe": copy.deepcopy(result["recipe"]), **plan}
