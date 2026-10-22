"""Actual CPU TAPNext inference from verified official source and weights."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import math
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tapnext_runtime import verify_layout, hash_file


def runtime(directory=None):
    verified = verify_layout(directory)
    expected = verified["lock"]["base_runtime"]
    versions = {name: importlib.metadata.version(name) for name in expected}
    if any(versions[name].split("+")[0] != version for name, version in expected.items()):
        raise ValueError("TAPNext needs the pinned learned Torch dependency versions")
    sys.path.insert(0, str(verified["source"]))
    import torch
    if sys.platform != "darwin" and torch.version.cuda is not None:
        raise ValueError("Managed TAPNext requires CPU-only Torch on Linux")
    model = verified["lock"]["models"]["tapnext"]
    public = {"available": True, "backend": "official-tapnext-pytorch", "device": "cpu",
              "mps_verified": False, "versions": versions, "lock_sha256": verified["lock_sha256"],
              "upstream_source_sha256": verified["upstream_source_sha256"],
              "models": {"tapnext": {k: model[k] for k in ("id", "sha256", "bytes", "license")}}}
    return verified, public


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def run(request, directory=None):
    from learned_tracking import validate_recipe
    recipe = validate_recipe(request["recipe"])
    if recipe["backend"] != "tapnext":
        raise ValueError("The TAPNext worker accepts only TAPNext requests")
    width, height, count = request["width"], request["height"], recipe["frame_count"]
    if any(type(v) is not int for v in (width, height)) or not (16 <= width <= 640 and 16 <= height <= 640):
        raise ValueError("TAPNext source dimensions exceed their bound")
    work = Path(request["directory"])
    frames_path = Path(request["frames"])
    if not work.is_absolute() or work.is_symlink() or not work.is_dir() or frames_path != work / "frames.rgb":
        raise ValueError("TAPNext needs its owned frame input and output directory")
    if frames_path.is_symlink() or not frames_path.is_file() or frames_path.stat().st_size != count * width * height * 3:
        raise ValueError("TAPNext did not receive every exact source-conformed RGB frame")
    verified, public = runtime(directory)
    import numpy as np
    import torch
    from PIL import Image, ImageDraw
    from tapnet.tapnext.tapnext_torch import TAPNext
    from tapnet.tapnext.tapnext_torch_utils import restore_model_from_jax_checkpoint
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    raw = frames_path.read_bytes()
    if len(raw) != count * width * height * 3:
        raise ValueError("TAPNext source frames changed during reading")
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(count, height, width, 3)
    started = time.monotonic()
    network = restore_model_from_jax_checkpoint(TAPNext(image_size=(256, 256)), verified["checkpoint"]).eval()
    write_json(work / "progress.json", {"progress": .2, "stage": "TAPNext checkpoint loaded"})
    query = torch.tensor([[[p["frame"] - recipe["frame_start"], p["y"] * 256, p["x"] * 256]
                           for p in recipe["points"]]], dtype=torch.float32)
    samples = [[] for _ in recipe["points"]]
    state = None
    with torch.inference_mode():
        for index, frame in enumerate(frames):
            picture = np.asarray(Image.fromarray(frame).resize((256, 256), Image.Resampling.BILINEAR), dtype=np.float32)
            video = torch.from_numpy(picture / 127.5 - 1).unsqueeze(0).unsqueeze(0)
            arguments = {"query_points": query} if index == 0 else {"state": state}
            tracks, _, visibility, state = network(video=video, **arguments)
            positions = tracks[0, 0].cpu().numpy()
            probabilities = visibility[0, 0, :, 0].sigmoid().cpu().numpy()
            for point, position, confidence, series in zip(recipe["points"], positions, probabilities, samples):
                y, x = float(position[0]) / 256, float(position[1]) / 256
                confidence = float(confidence)
                if not all(math.isfinite(v) for v in (x, y, confidence)):
                    raise ValueError("TAPNext returned non-finite points or visibility")
                before_query = recipe["frame_start"] + index < point["frame"]
                visible = not before_query and confidence > .5 and 0 <= x <= 1 and 0 <= y <= 1
                series.append({"frame": recipe["frame_start"] + index, "x": x if visible else None,
                               "y": y if visible else None, "visible": visible,
                               "confidence": 0 if before_query else confidence})
            write_json(work / "progress.json", {"progress": .2 + .75 * (index + 1) / count, "stage": "TAPNext recurrent point inference"})
    model = verified["lock"]["models"]["tapnext"]
    if hash_file(verified["checkpoint"], model["bytes"]) != (model["sha256"], model["bytes"]):
        raise ValueError("TAPNext checkpoint changed during inference")
    preview = Image.fromarray(frames[0]).copy()
    draw = ImageDraw.Draw(preview)
    for series in samples:
        locations = [(sample["x"] * width, sample["y"] * height) for sample in series if sample["visible"]]
        if len(locations) > 1:
            draw.line(locations, fill=(255, 200, 40), width=2)
        for x, y in locations:
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline=(255, 80, 40), width=2)
    preview.save(work / "preview.png")
    result = {"backend": "tapnext", "model": model["id"], "device": "cpu", "width": width, "height": height,
              "frame_count": count, "inference_seconds": time.monotonic() - started,
              "checkpoint_sha256": model["sha256"], "runtime": public,
              "tracks": [{"id": point["id"], "reference_frame": point["frame"], "samples": series}
                         for point, series in zip(recipe["points"], samples)],
              "analysis_input": "project-conformed RGB8 resized to256x256; normalized[-1,1]",
              "internal_model_resolution": [256, 256],
              "visibility": "official visible-logit sigmoid >0.5; before-query/outside-source samples invisible",
              "architecture": "official recurrent TRecViT-B; independent TAPNext checkpoint"}
    write_json(work / "worker-result.json", result)
    write_json(work / "progress.json", {"progress": 1, "stage": "TAPNext inference complete"})
    return result


def install_probe(directory=None):
    import numpy as np
    yy, xx = np.mgrid[:256, :256]
    background = np.stack([35 + (xx // 16) % 2 * 8, 47 + (yy // 16) % 2 * 8,
                           70 + (xx // 32 + yy // 32) % 2 * 9], axis=-1).astype(np.uint8)
    texture = np.random.default_rng(72351).integers(0, 256, (52, 52, 3), dtype=np.uint8)
    texture[:, :, 0] = 160 + texture[:, :, 0] // 3
    texture[:, :, 1:] //= 3
    frames = []
    for index in range(2):
        cx, cy = 75 + 14 * index, 135
        image = background.copy()
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= 24 ** 2
        region = image[cy - 26:cy + 26, cx - 26:cx + 26]
        local = mask[cy - 26:cy + 26, cx - 26:cx + 26]
        region[local] = texture[local]
        frames.append(image)
    with tempfile.TemporaryDirectory(prefix="cinematicum-TAPNext-ENGINE-TEST-") as temporary:
        work = Path(temporary)
        raw = work / "frames.rgb"
        raw.write_bytes(np.stack(frames).tobytes())
        result = run({"recipe": {"version": 1, "backend": "tapnext", "frame_start": 0, "frame_count": 2,
                                 "points": [{"id": "probe", "frame": 0, "x": 75 / 256, "y": 135 / 256}]},
                      "width": 256, "height": 256, "directory": str(work), "frames": str(raw)}, directory)
    samples = result["tracks"][0]["samples"]
    errors = [math.hypot(sample["x"] * 256 - (75 + 14 * index), sample["y"] * 256 - 135)
              for index, sample in enumerate(samples) if sample["visible"]]
    checks = {"actual_checkpoint_motion": len(errors) == 2 and max(errors) < 3,
              "actual_learned_visibility": len(samples) == 2 and all(s["visible"] and s["confidence"] > .5 for s in samples)}
    if not all(checks.values()):
        raise ValueError("The actual TAPNext checkpoint failed its independent motion oracle")
    return {**result["runtime"], "checks": checks, "maximum_error_pixels": max(errors),
            "checkpoint_sha256": result["checkpoint_sha256"],
            "scope": "Synthetic two-frame checkpoint readiness; production tracking is not certified"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--install-probe", action="store_true")
    args = parser.parse_args()
    try:
        if args.install_probe:
            result = install_probe(args.runtime)
        elif args.capabilities:
            result = runtime(args.runtime)[1]
        elif args.request:
            if args.request.is_symlink() or args.request.stat().st_size > 128 * 1024:
                raise ValueError("TAPNext request exceeds its owned input bound")
            measured = run(json.loads(args.request.read_text()), args.runtime)
            result = {"complete": True, "backend": "tapnext", "frame_count": measured["frame_count"]}
        else:
            raise ValueError("Choose TAPNext capability verification or a frozen request")
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
