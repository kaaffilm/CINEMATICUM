"""Bounded photograph geometry through the installed OpenCV/NumPy runtime.

The application and OCIO interpreter need not import OpenCV. A child of the
owned imaging process consumes hashed float snapshots and produces hashed
linear pixels; cancellation kills the same process group as every other image
codec. Nothing is installed or downloaded by this workflow.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from imaging import MAX_PIXELS, _hash_file, _json_bytes

MAX_IMAGE_PIXELS = 8_388_608
MAX_STACK_PIXELS = 25_165_824
MAX_PANORAMA_IMAGES = 8
ANALYSIS_EDGE = 1536
WORKER = Path(__file__).with_name("still_photo_worker.py")


def needed(recipe):
    return recipe["operation"] == "panorama" or (recipe["operation"] == "hdr_merge" and (
        recipe.get("alignment", "none") != "none" or recipe.get("deghost", "none") != "none"
        or recipe["input_transfer"] == "measured"))


def environment():
    result = {key: value for key, value in os.environ.items() if not key.startswith(("PYTHON", "OCIO"))}
    result.update(OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", VECLIB_MAXIMUM_THREADS="2")
    return result


def capabilities(python=None):
    from imaging import find_imaging_python
    explicit = python or os.environ.get("CINEMATICUM_TRACKING_PYTHON")
    choices = [explicit] if python else [explicit,
        str(Path.home() / "Library/Application Support/CINEMATICUM/Tracking/py313-v1/bin/python"),
        find_imaging_python()]
    seen, errors = set(), []
    for value in choices:
        if not value or value in seen:
            continue
        seen.add(value)
        path = Path(value).expanduser()
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            continue
        try:
            run = subprocess.run([str(path), "-I", "-B", str(WORKER), "--capabilities"],
                                 env=environment(), capture_output=True, text=True, timeout=12)
            if run.returncode or len(run.stdout) > 65536:
                raise ValueError(run.stderr[-600:] or "The photograph runtime probe failed.")
            result = json.loads(run.stdout)
            if not result.get("available") or not result.get("actual_operations_verified"):
                raise ValueError("The photograph runtime did not verify its numerical operations.")
            return {**result, "python": str(path), "max_image_pixels": MAX_IMAGE_PIXELS,
                    "max_stack_pixels": MAX_STACK_PIXELS, "max_panorama_images": MAX_PANORAMA_IMAGES,
                    "analysis_edge": ANALYSIS_EDGE, "max_output_pixels": MAX_PIXELS}
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))
    return {"available": False, "reason": "Install the CINEMATICUM Tracking runtime for photograph alignment, "
            "deghosting, measured response and planar panoramas. " + (errors[-1] if errors else "No isolated OpenCV runtime was found.")}


def process_images(images, recipe, scratch, python, np, progress=None):
    """Called by image_worker inside its private project .building directory."""
    scratch = Path(scratch)
    if scratch.is_symlink() or not scratch.is_dir() or not scratch.name.startswith(".building-"):
        raise ValueError("Photograph processing requires its private owned imaging workspace.")
    inputs, total = [], 0
    for index, image in enumerate(images):
        pixels = np.asarray(image, dtype="<f4")
        if pixels.ndim != 3 or pixels.shape[2] != 4:
            raise ValueError("Photograph snapshots must contain RGBA pixels.")
        height, width = pixels.shape[:2]
        total += width * height
        if width * height > MAX_IMAGE_PIXELS or total > MAX_STACK_PIXELS:
            raise ValueError("Enhanced photograph processing is limited to 8.4 million pixels per image and 25.2 million input pixels in total.")
        name = "photo-source-%02d.f32le" % index
        path = scratch / name
        with path.open("xb") as output:
            output.write(pixels.tobytes(order="C"))
        digest, size = _hash_file(path)
        inputs.append({"filename": name, "width": width, "height": height, "sha256": digest, "size": size})
        if progress:
            progress(.08 + .15 * (index + 1) / (len(recipe["images"]) if recipe["operation"] == "panorama" else len(recipe["brackets"])))
    request = {"workspace": str(scratch), "recipe": recipe, "inputs": inputs}
    if not isinstance(python, str) or not Path(python).is_absolute() or not os.access(python, os.X_OK):
        raise ValueError("The photograph worker requires its discovered isolated interpreter.")
    # Do not create a new session: the owning image job cancels this worker and
    # every codec in one process group, including a long OpenCV calculation.
    run = subprocess.run([python, "-I", "-B", str(WORKER)], input=_json_bytes(request),
                         env=environment(), capture_output=True, timeout=240)
    if len(run.stdout) > 2 * 1024 * 1024:
        raise ValueError("The photograph worker returned an oversized analysis record.")
    try:
        result = json.loads(run.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("The photograph worker did not return its result: " + run.stderr.decode(errors="replace")[-1000:]) from exc
    if run.returncode or result.get("error"):
        raise ValueError(result.get("error", "Photograph processing failed."))
    width, height = result.get("width"), result.get("height")
    if (type(width) is not int or type(height) is not int or not 1 <= width <= 16384
            or not 1 <= height <= 16384 or width * height > MAX_PIXELS):
        raise ValueError("The photograph worker returned an invalid output size.")
    def read(name, expected_size):
        descriptor = result.get(name)
        filename = {"pixels": "photo-result.f32le", "motion": "photo-motion.u8"}[name]
        path = scratch / filename
        if not isinstance(descriptor, dict) or path.is_symlink() or descriptor.get("filename") != filename:
            raise ValueError("The photograph worker returned an invalid owned artifact.")
        digest, size = _hash_file(path, MAX_PIXELS * 16)
        if size != expected_size or digest != descriptor.get("sha256") or size != descriptor.get("size"):
            raise ValueError("The photograph worker pixels do not match their result identity.")
        return path.read_bytes()
    rgba = np.frombuffer(read("pixels", width * height * 16), dtype="<f4").reshape(height, width, 4).copy()
    if not np.isfinite(rgba).all() or np.max(np.abs(rgba[..., :3])) > 1e20 or np.any((rgba[..., 3] < 0) | (rgba[..., 3] > 1)):
        raise ValueError("Photograph processing returned invalid linear pixels.")
    motion = None
    if recipe["operation"] == "hdr_merge" and recipe.get("deghost") == "reference":
        motion = np.frombuffer(read("motion", width * height), dtype=np.uint8).reshape(height, width).copy()
        if np.any((motion != 0) & (motion != 255)):
            raise ValueError("The measured motion mask is not binary.")
    if progress:
        progress(.52)
    return rgba[..., :3], rgba[..., 3], result["details"], motion
