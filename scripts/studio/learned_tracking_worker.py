"""Isolated, checkpoint-backed SAM2.1 and TAPIR inference.

No optional model is imported by the Studio server. Upstream source and weight
bytes must match the shipped lock before this worker imports either package.
The official CPU graph is used without model compilation or downloaded code.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import stat
import sys
import sysconfig
import tempfile
import time

LOCK = Path(__file__).with_name("learned-runtime-lock.json")
MAX_RGB_BYTES = 32 * 640 * 640 * 3
MAX_REQUEST_BYTES = 128 * 1024


def _read(path, maximum):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError("Learned inference requires a bounded regular input file")
        value = stream.read(maximum + 1)
        if len(value) != info.st_size or len(value) > maximum:
            raise ValueError("Learned inference input changed while reading")
        return value


def _hash(path, maximum):
    path = Path(path)
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Learned runtime inputs may not traverse symbolic links")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    digest = hashlib.sha256()
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise ValueError("Learned runtime requires bounded regular source and weight files")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
        if (info.st_size, info.st_mtime_ns, info.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ValueError("Learned runtime bytes changed while verifying")
    return digest.hexdigest(), info.st_size


def _model_directory(value=None):
    name = value or os.environ.get("CINEMATICUM_LEARNED_MODELS")
    path = Path(name).expanduser() if name else Path(sys.prefix) / "share/cinematicum-learned/models"
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise ValueError("Install the pinned learned-model checkpoints before inference")
    # The managed public runtime entry is a stable link to an immutable owned
    # version. Resolve that parent once; individual checkpoint files must still
    # be regular nonlinks and match the exact official digest.
    return path.resolve(strict=True)


def verify_runtime(models_dir=None, selected=None):
    lock = json.loads(_read(LOCK, 256 * 1024))
    if lock.get("schema") != "cinematicum-learned-runtime-lock" or lock.get("version") != 1:
        raise ValueError("Unsupported learned runtime lock")
    site = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    source_digest = hashlib.sha256()
    for source in lock["sources"]:
        package = source["files"][0]["package"]
        records = [record for record in source["files"] if record["path"].startswith(package + "/")]
        expected = {record["path"] for record in records}
        actual = {str(path.relative_to(site)) for path in (site / package).rglob("*")
                  if path.is_file() and path.suffix in {".py", ".yaml", ".yml"}}
        expected_code = {name for name in expected if Path(name).suffix in {".py", ".yaml", ".yml"}}
        if actual != expected_code:
            raise ValueError("The installed learned model source inventory differs from its pinned upstream code")
        for record in records:
            digest, size = _hash(site / record["path"], 8 * 1024 * 1024)
            if (digest, size) != (record["sha256"], record["size"]):
                raise ValueError("The installed learned model source differs from its pinned upstream bytes")
            source_digest.update((record["path"] + "\0" + digest + "\n").encode())
    directory = _model_directory(models_dir)
    models = {}
    for key, record in lock["models"].items():
        if selected is not None and key != selected:
            continue
        path = directory / record["name"]
        digest, size = _hash(path, record["bytes"])
        if (digest, size) != (record["sha256"], record["bytes"]):
            raise ValueError("The learned checkpoint differs from its exact official model hash")
        models[key] = {"id": record["id"], "sha256": digest, "bytes": size,
                       "license": record["license"], "path": str(path)}
    versions = {name: importlib.metadata.version(name) for name in
                ("torch", "torchvision", "numpy", "hydra-core", "einshape", "dm-tree")}
    expected = {"torch": "2.8.0", "torchvision": "0.23.0", "numpy": "2.3.5",
                "hydra-core": "1.3.2", "einshape": "1.0", "dm-tree": "0.1.9"}
    if any(versions[key].split("+")[0] != version for key, version in expected.items()):
        raise ValueError("The learned runtime versions differ from the verified dependency lock")
    import torch
    if sys.platform != "darwin" and torch.version.cuda is not None:
        raise ValueError("The managed Linux learned runtime requires official CPU-only Torch wheels")
    return {"available": True, "backend": "official-pytorch-checkpoints", "device": "cpu",
            "models": models, "versions": versions, "upstream_source_sha256": source_digest.hexdigest(),
            "lock_sha256": hashlib.sha256(_read(LOCK, 256 * 1024)).hexdigest(),
            "mps_verified": False, "cuda_extension": False}


def _write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, path)


def _progress(directory, fraction, stage):
    _write_json(Path(directory) / "progress.json", {"progress": fraction, "stage": stage})


def _sam2(frames, recipe, directory, model):
    import numpy as np
    from PIL import Image
    import torch
    from sam2.build_sam import build_sam2_video_predictor

    count, height, width = frames.shape[:3]
    folder = directory / "sam-frames"
    folder.mkdir()
    for index, frame in enumerate(frames):
        # This is the official predictor's supported JPEG-frame input route.
        # Its analysis conversion is recorded; source/export RGB is untouched.
        Image.fromarray(frame).save(folder / f"{index:05d}.jpg", quality=100, subsampling=0)
    predictor = build_sam2_video_predictor("configs/sam2.1/sam2.1_hiera_t.yaml", model["path"],
                                           device="cpu", apply_postprocessing=False)
    _progress(directory, .12, "SAM2 checkpoint loaded")
    measured = {}
    with torch.inference_mode():
        state = predictor.init_state(str(folder), offload_video_to_cpu=True, offload_state_to_cpu=True)
        for prompt in recipe["prompts"]:
            points = np.array([[point["x"] * width, point["y"] * height] for point in prompt["points"]], dtype=np.float32)
            labels = np.array([point["label"] for point in prompt["points"]], dtype=np.int32)
            box = np.array(prompt["box"], dtype=np.float32) * [width, height, width, height] if "box" in prompt else None
            predictor.add_new_points_or_box(state, frame_idx=prompt["frame"] - recipe["frame_start"],
                obj_id=1, points=points if len(points) else None, labels=labels if len(labels) else None, box=box)
        first = min(prompt["frame"] for prompt in recipe["prompts"]) - recipe["frame_start"]
        for index, object_ids, scores in predictor.propagate_in_video(state, start_frame_idx=first):
            if object_ids != [1] or scores.shape != (1, 1, height, width):
                raise ValueError("SAM2 returned an unexpected object or mask shape")
            values = scores[0, 0].cpu().numpy()
            if not np.isfinite(values).all():
                raise ValueError("SAM2 returned non-finite mask scores")
            measured[index] = values > 0
            _progress(directory, .15 + .75 * len(measured) / count, "SAM2 video propagation")
        if first:
            for index, object_ids, scores in predictor.propagate_in_video(state, start_frame_idx=first, reverse=True):
                values = scores[0, 0].cpu().numpy()
                if object_ids != [1] or values.shape != (height, width) or not np.isfinite(values).all():
                    raise ValueError("SAM2 returned invalid reverse mask scores")
                measured[index] = values > 0
                _progress(directory, .15 + .75 * len(measured) / count, "SAM2 reverse propagation")
    if set(measured) != set(range(count)):
        raise ValueError("SAM2 did not return every requested conformed frame")
    masks = np.stack([measured[index] for index in range(count)])
    # The raw matte is an internal temporary, encoded by the owned FFmpeg
    # process; it is never an alleged model or stand-in for deep transparency.
    with (directory / "mask.rgba64le").open("wb") as stream:
        for mask in masks:
            # Encode the two actual binary values directly in the high-depth
            # domain. FFmpeg's BGRA8→planar16 negotiation does not preserve
            # fully opaque alpha exactly on every supported build.
            rgba = np.full((height, width, 4), 65535, dtype=np.dtype("<u2"))
            rgba[:, :, 3] = mask.astype(np.uint16) * 65535
            stream.write(rgba.tobytes())
    preview = np.concatenate([frames[0], (masks[0].astype(np.uint8) * 255)[:, :, None]], axis=-1)
    Image.fromarray(preview).save(directory / "preview.png")
    return {"mask_frames": [{"frame": recipe["frame_start"] + index, "foreground_pixels": int(mask.sum()),
                            "coverage": float(mask.mean())} for index, mask in enumerate(masks)],
            "mask_type": "binary-object-alpha", "mask_logit_threshold": 0,
            "analysis_input": "project-conformed RGB8; official JPEG quality100/subsampling0 loader",
            "internal_model_resolution": [1024, 1024], "object_id": 1,
            "postprocessing": "optional CUDA connected-component postprocessing disabled"}


def _tapir(frames, recipe, directory, model):
    import numpy as np
    from PIL import Image, ImageDraw
    import torch
    from tapnet.torch.tapir_model import TAPIR

    count, height, width = frames.shape[:3]
    network = TAPIR(pyramid_level=0, extra_convs=False, feature_extractor_chunk_size=2)
    weights = torch.load(model["path"], map_location="cpu", weights_only=True)
    network.load_state_dict(weights, strict=True)
    del weights
    network.eval()
    _progress(directory, .2, "TAPIR checkpoint loaded")
    images = np.stack([np.array(Image.fromarray(frame).resize((256, 256), Image.Resampling.BILINEAR)) for frame in frames])
    video = torch.from_numpy(images).float()[None] / 127.5 - 1
    queries = torch.tensor([[[point["frame"] - recipe["frame_start"], point["y"] * 256, point["x"] * 256]
                             for point in recipe["points"]]], dtype=torch.float32)
    with torch.inference_mode():
        output = network(video, queries, query_chunk_size=4)
    tracks = output["tracks"][0].cpu().numpy() / 256
    confidences = ((1 - output["occlusion"].sigmoid()) * (1 - output["expected_dist"].sigmoid()))[0].cpu().numpy()
    if tracks.shape != (len(recipe["points"]), count, 2) or not np.isfinite(tracks).all() or not np.isfinite(confidences).all():
        raise ValueError("TAPIR returned invalid learned point samples")
    results = []
    preview = Image.fromarray(frames[0])
    draw = ImageDraw.Draw(preview)
    colors = ("#65ff89", "#ffb53d", "#51d7ff", "#f58cff")
    for ordinal, point in enumerate(recipe["points"]):
        samples = []
        for index, ((x, y), confidence) in enumerate(zip(tracks[ordinal], confidences[ordinal])):
            visible = bool(confidence > .5 and 0 <= x <= 1 and 0 <= y <= 1)
            samples.append({"frame": recipe["frame_start"] + index, "visible": visible,
                            "x": float(x) if visible else None, "y": float(y) if visible else None,
                            "confidence": float(confidence)})
            if visible:
                px, py = float(x) * width, float(y) * height
                draw.ellipse((px - 2, py - 2, px + 2, py + 2), fill=colors[ordinal % len(colors)])
        results.append({"id": point["id"], "reference_frame": point["frame"], "samples": samples})
    preview.save(directory / "preview.png")
    _progress(directory, .95, "TAPIR trajectory and occlusion inference complete")
    return {"tracks": results, "analysis_input": "project-conformed RGB8 resized to256x256; normalized[-1,1]",
            "internal_model_resolution": [256, 256],
            "visibility": "(1-sigmoid(occlusion))*(1-sigmoid(expected_dist)) >0.5; outside-source points invisible",
            "architecture": {"pyramid_level": 0, "extra_convs": False}}


def run(request, models_dir=None):
    recipe = request["recipe"]
    width, height, count = request["width"], request["height"], recipe["frame_count"]
    if any(type(value) is not int for value in (width, height, count)) or not (16 <= width <= 640 and 16 <= height <= 640 and 1 <= count <= 32):
        raise ValueError("Learned inference dimensions exceed their accepted bound")
    directory = Path(request["directory"])
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise ValueError("Learned inference needs its owned temporary directory")
    runtime = verify_runtime(models_dir, recipe["backend"])
    import numpy as np
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    raw = _read(request["frames"], MAX_RGB_BYTES)
    if len(raw) != count * height * width * 3:
        raise ValueError("Learned inference did not receive every exact conformed RGB frame")
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(count, height, width, 3)
    started = time.monotonic()
    backend = recipe["backend"]
    model = runtime["models"][backend]
    result = _sam2(frames, recipe, directory, model) if backend == "sam2" else _tapir(frames, recipe, directory, model)
    # No result is accepted if the model was replaced during inference.
    if _hash(model["path"], model["bytes"]) != (model["sha256"], model["bytes"]):
        raise ValueError("The learned checkpoint changed during inference")
    public_runtime = {**runtime, "models": {key: {k: v for k, v in value.items() if k != "path"}
                                             for key, value in runtime["models"].items()}}
    result.update(backend=backend, model=model["id"], device="cpu", width=width, height=height,
                  frame_count=count, inference_seconds=time.monotonic() - started,
                  checkpoint_sha256=model["sha256"], runtime=public_runtime)
    _write_json(directory / "worker-result.json", result)
    _progress(directory, 1, "Learned inference complete")
    return result


def install_probe(backend, models_dir=None):
    """Exercise actual official weights on a small independent motion oracle."""
    runtime = verify_runtime(models_dir, backend)
    import numpy as np
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    yy, xx = np.mgrid[:160, :256]
    background = np.stack([35+(xx//16)%2*8,47+(yy//16)%2*8,
                           70+(xx//32+yy//32)%2*9],axis=-1).astype(np.uint8)
    texture = np.random.default_rng(72351).integers(0,256,(52,52,3),dtype=np.uint8)
    texture[:,:,0]=160+texture[:,:,0]//3;texture[:,:,1]//=3;texture[:,:,2]//=3
    count=1 if backend=="sam2" else 2
    frames=[];oracles=[];centers=[]
    for index in range(count):
        cx,cy=45+14*index,85;centers.append((cx,cy))
        image=background.copy();mask=(xx-cx)**2+(yy-cy)**2<=24**2
        region=image[cy-26:cy+26,cx-26:cx+26];local=mask[cy-26:cy+26,cx-26:cx+26]
        region[local]=texture[local]
        frames.append(image);oracles.append(mask)
    recipe={"version":1,"backend":backend,"frame_start":0,"frame_count":count}
    if backend=="sam2":
        recipe["prompts"]=[{"frame":0,"points":[{"x":45/256,"y":85/160,"label":1}],
                            "box":[20/256,60/160,70/256,110/160]}]
    else:
        recipe["points"]=[{"id":"probe","frame":0,"x":45/256,"y":85/160}]
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix="cinematicum-learned-install-") as temporary:
        directory=Path(temporary);model=runtime["models"][backend]
        result=(_sam2 if backend=="sam2" else _tapir)(np.stack(frames),recipe,directory,model)
        if backend=="sam2":
            alpha=np.frombuffer(_read(directory/"mask.rgba64le",256*160*8),dtype="<u2").reshape(160,256,4)[:,:,3]
            actual=alpha>0;oracle=oracles[0]
            metric=float((actual&oracle).sum()/(actual|oracle).sum())
            checks={"actual_checkpoint_mask":metric>.95,"binary_full_depth_alpha":set(np.unique(alpha).tolist())=={0,65535}}
            numerical={"intersection_over_union":metric}
        else:
            samples=result["tracks"][0]["samples"]
            errors=[math.hypot(sample["x"]*256-center[0],sample["y"]*160-center[1])
                    for sample,center in zip(samples,centers) if sample["visible"]]
            metric=max(errors) if errors else None
            checks={"actual_checkpoint_motion":len(errors)==count and metric<2,
                    "actual_learned_visibility":all(sample["visible"] and sample["confidence"]>.5 for sample in samples)}
            numerical={"maximum_visible_error_pixels":metric}
    if not all(checks.values()): raise ValueError("The actual learned checkpoint failed its small image/motion readiness oracle")
    return {"available":True,"backend":backend,"device":"cpu","mps_verified":False,"checks":checks,
            "numerical":numerical,"checkpoint_sha256":runtime["models"][backend]["sha256"],
            "upstream_source_sha256":runtime["upstream_source_sha256"],"lock_sha256":runtime["lock_sha256"],
            "seconds":time.monotonic()-started,"scope":"Small actual checkpoint readiness test; production footage quality is not certified"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--request")
    parser.add_argument("--models-dir")
    parser.add_argument("--install-probe", choices=("sam2", "tapir"))
    arguments = parser.parse_args()
    try:
        if arguments.install_probe:
            result = install_probe(arguments.install_probe, arguments.models_dir)
        elif arguments.capabilities:
            result = verify_runtime(arguments.models_dir)
            for model in result["models"].values(): model.pop("path", None)
        elif arguments.request:
            result = run(json.loads(_read(arguments.request, MAX_REQUEST_BYTES)), arguments.models_dir)
            result = {"complete": True, "backend": result["backend"], "frame_count": result["frame_count"]}
        else:
            raise ValueError("Choose a learned-runtime probe or an owned request")
        print(json.dumps(result, allow_nan=False, sort_keys=True))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
