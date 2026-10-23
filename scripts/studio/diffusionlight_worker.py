"""Isolated offline worker for the unmodified official DiffusionLight stages.

No dependency, repository or model download is performed. A doctor response
proves imports and local byte identities only; it never claims inference.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location("_diffusionlight_controller", Path(__file__).with_name("diffusionlight.py"))
controller = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(controller)

PACKAGES = {"torch": "2.0.1", "torchvision": "0.15.2", "torchaudio": "2.0.2", "diffusers": "0.21.0",
            "transformers": "4.36.0", "huggingface_hub": "0.19.4", "accelerate": "0.21.0",
            "numpy": "1.24.1", "scikit-image": "0.21.0", "Pillow": "10.2.0", "skylibs": "0.7.4",
            "OpenEXR": "1.3.9", "natsort": "8.4.0", "tqdm": "4.66.1", "imageio": "2.31.1"}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def read_json(path, limit=8 * 1024 * 1024):
    path = controller._path(path)
    if path.stat().st_size > limit:
        raise ValueError("DiffusionLight JSON exceeds its size bound.")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("DiffusionLight metadata must be an object.")
    return value


def blob_sha1(path):
    value = hashlib.sha1()
    value.update(("blob %d\0" % path.stat().st_size).encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def relative(value):
    if not isinstance(value, str):
        raise ValueError("DiffusionLight manifest paths must be strings.")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in {".", ".."} for p in path.parts) or str(path) != value or "\\" in value:
        raise ValueError("DiffusionLight manifest paths must be canonical relative paths.")
    return path


def source_snapshot(root, destination):
    """Copy only authenticated Python blobs, preventing import shadowing."""
    lock_path = Path(__file__).with_name("diffusionlight-source-lock.json")
    if controller.digest(lock_path) != controller.SOURCE_LOCK_SHA256:
        raise ValueError("The shipped DiffusionLight source lock changed.")
    lock = read_json(lock_path)
    records = []
    for item in lock["files"]:
        name = relative(item["path"])
        source = controller._path(root / str(name))
        if source.stat().st_size != item["size"] or blob_sha1(source) != item["git_blob_sha1"]:
            raise ValueError("DiffusionLight upstream source differs from its official pinned blob: " + str(name))
        target = destination / str(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if blob_sha1(target) != item["git_blob_sha1"]:
            raise ValueError("DiffusionLight source changed while creating its import snapshot.")
        records.append({"path": str(name), "sha256": controller.digest(target)})
    # Upstream uses a namespace package. A local empty marker ensures that a
    # similarly named installed package cannot replace these authenticated files.
    (destination / "relighting/__init__.py").write_bytes(b"")
    return lock, records


def verify_models(runtime, lock):
    path = Path(runtime["model_manifest"])
    if controller.digest(path) != runtime["model_manifest_sha256"]:
        raise ValueError("DiffusionLight model manifest changed before worker verification.")
    manifest = read_json(path)
    if manifest.get("schema") != "cinematicum-diffusionlight-models" or manifest.get("version") != 1:
        raise ValueError("Unsupported DiffusionLight local model manifest.")
    models = manifest.get("models")
    if not isinstance(models, dict) or set(models) != {*lock["models"], "lora"}:
        raise ValueError("DiffusionLight requires SDXL, depth ControlNet, fixed VAE, DPT and exposure LoRA.")
    verified = {}
    for name, repository in lock["models"].items():
        entry = models[name]
        if not isinstance(entry, dict) or entry.get("repository") != repository:
            raise ValueError("DiffusionLight model repository differs from the official model: " + name)
        revision = entry.get("revision")
        if not isinstance(revision, str) or len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
            raise ValueError("DiffusionLight model revisions must be immutable commit hashes.")
        root = controller._path(entry.get("root"), True)
        files = entry.get("files")
        if not isinstance(files, list) or not 1 <= len(files) <= 2048:
            raise ValueError("DiffusionLight model file inventory is missing or too large.")
        names = set()
        for item in files:
            if not isinstance(item, dict):
                raise ValueError("DiffusionLight model file entry must be an object.")
            member = str(relative(item.get("path")))
            if member in names or not controller._sha(item.get("sha256")) or type(item.get("bytes")) is not int or item["bytes"] < 0:
                raise ValueError("DiffusionLight model file identity is incomplete or ambiguous.")
            names.add(member)
            source = controller._path(root / member)
            if source.stat().st_size != item["bytes"] or controller.digest(source) != item["sha256"]:
                raise ValueError("DiffusionLight weight or configuration differs from its trusted manifest: " + name + "/" + member)
        actual = set()
        for member in root.rglob("*"):
            if member.is_symlink():
                raise ValueError("DiffusionLight model inventories cannot contain symbolic links.")
            if member.is_file():
                actual.add(member.relative_to(root).as_posix())
        if actual != names:
            raise ValueError("DiffusionLight model directory has missing or unmanifested files: " + name)
        if any(PurePosixPath(n).suffix in {".py", ".pyc", ".pth", ".so", ".dylib", ".pyd"} for n in names):
            raise ValueError("DiffusionLight model directories cannot supply executable code.")
        verified[name] = {"root": str(root), "repository": repository, "revision": revision, "files": files}
    lora = models["lora"]
    if not isinstance(lora, dict):
        raise ValueError("DiffusionLight exposure LoRA entry must be an object.")
    lora_path = controller._path(lora.get("path"))
    if lora_path.stat().st_size != lock["lora"]["size"] or blob_sha1(lora_path) != lock["lora"]["git_blob_sha1"]:
        raise ValueError("DiffusionLight exposure LoRA differs from the official checkpoint-2500 safetensors.")
    verified["lora"] = {"repository": lock["lora"]["repository"], "upstream_path": lock["lora"]["path"],
                        "git_blob_sha1": lock["lora"]["git_blob_sha1"], "bytes": lock["lora"]["size"],
                        "path": str(lora_path), "sha256": controller.digest(lora_path)}
    return verified


def runtime_versions(device):
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError("The official pinned DiffusionLight environment requires Python 3.11.")
    versions = {name: importlib.metadata.version(name) for name in PACKAGES}
    for name, expected in PACKAGES.items():
        if versions[name].split("+", 1)[0] != expected:
            raise RuntimeError("DiffusionLight requires the upstream pinned %s==%s runtime." % (name, expected))
    import torch
    import ezexr
    from scipy.special import sph_harm  # Imported by the official ball code.
    if device == "cuda" and (not torch.cuda.is_available() or torch.version.cuda != "11.8"):
        raise RuntimeError("The selected DiffusionLight CUDA device requires an available CUDA 11.8 Torch build.")
    return versions


def artifact(path, root):
    if path.is_symlink() or not path.is_file():
        raise ValueError("DiffusionLight output is not an owned regular artifact.")
    return {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": controller.digest(path)}


def normalize_image(request, dataset):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 16 * 1024 * 1024
    source_path = controller._path(request["source_image"])
    if controller.digest(source_path) != request["source_sha256"]:
        raise ValueError("DiffusionLight input photograph differs from its admitted identity.")
    with Image.open(source_path) as source:
        if source.format not in {"PNG", "JPEG"} or getattr(source, "n_frames", 1) != 1 or source.width * source.height > Image.MAX_IMAGE_PIXELS:
            raise ValueError("DiffusionLight input must be one PNG/JPEG photograph of at most 16 megapixels.")
        image = ImageOps.exif_transpose(source).convert("RGBA")
        if image.getchannel("A").getextrema() != (255, 255):
            raise ValueError("DiffusionLight photographs must be explicitly opaque.")
        original_size = image.size
        fitted = ImageOps.contain(image.convert("RGB"), (1024, 1024), Image.Resampling.LANCZOS)
        prepared = Image.new("RGB", (1024, 1024), (0, 0, 0))
        offset = ((1024 - fitted.width) // 2, (1024 - fitted.height) // 2)
        prepared.paste(fitted, offset)
        output = dataset / "input.png"
        prepared.save(output)
    return {"source_sha256": request["source_sha256"], "source_dimensions_after_exif": list(original_size),
            "input_dimensions": [1024, 1024], "fitted_dimensions": list(fitted.size), "offset": list(offset),
            "preparation": "EXIF orientation, opaque RGB8, aspect-preserving Lanczos fit and centered black padding",
            "prepared_sha256": controller.digest(output)}


def validate_hdr(path, height=256):
    import numpy as np
    import ezexr
    if not path.is_file() or path.read_bytes()[:4] != b"\x76\x2f\x31\x01":
        raise ValueError("DiffusionLight did not produce an actual OpenEXR file.")
    image = ezexr.imread(str(path))
    if image.shape != (height, height * 2, 3) or image.dtype != np.float32 or not np.isfinite(image).all() or (image < 0).any():
        raise ValueError("DiffusionLight HDR must decode as finite nonnegative RGB float32 latitude-longitude pixels.")
    if float(image.max()) <= 0 or float(image.std()) <= 1e-8:
        raise ValueError("DiffusionLight produced an empty or constant environment; no useful lighting output is accepted.")
    return {"width": image.shape[1], "height": image.shape[0], "channels": 3, "dtype": str(image.dtype),
            "minimum": float(image.min()), "maximum": float(image.max()), "mean": float(image.mean()),
            "standard_deviation": float(image.std()), "fraction_above_one": float((image > 1).mean())}


def infer(request, snapshot, lock, models, versions):
    import numpy as np
    import torch
    from PIL import Image
    import inpaint
    import ball2envmap
    import exposure2hdr
    import relighting.argument as argument
    import relighting.inpainter as inpainter
    started = time.monotonic()
    settings = controller.options(request.get("settings"))
    output = controller._path(request["output_dir"], True)
    if {item.name for item in output.iterdir()} != {"worker.log", "progress.json"}:
        raise ValueError("DiffusionLight output must contain only its new owned log and initial execution state.")
    work = output / "work"
    work.mkdir()
    dataset = work / "input"
    dataset.mkdir()
    normalization = normalize_image(request, dataset)
    # The official control-signal selector recognizes depth from the model path.
    # This owned alias points only at a fully verified, app-configured directory.
    controlnet_alias = work / "controlnet-depth"
    controlnet_alias.symlink_to(models["controlnet_depth"]["root"], target_is_directory=True)
    lora = work / "lora"
    lora.mkdir()
    shutil.copyfile(models["lora"]["path"], lora / "pytorch_lora_weights.safetensors")
    argument.SD_MODELS["sdxl"] = models["sdxl"]["root"]
    argument.CONTROLNET_MODELS["sdxl"] = str(controlnet_alias)
    argument.VAE_MODELS["sdxl"] = models["vae"]["root"]
    inpainter.DEPTH_ESTIMATOR = models["depth"]["root"]
    inpaint_output = output / "inpaint"
    argv = ["inpaint.py", "--dataset", str(dataset), "--output_dir", str(inpaint_output),
            "--model_option", "sdxl", "--lora_path", str(lora), "--lora_scale", "0.75",
            "--seed", str(settings["seed"]), "--denoising_step", str(settings["steps"]),
            "--algorithm", settings["algorithm"], "--no_torch_compile", "--no_random_loader",
            "--no_save_intermediate", "--cache_dir", str(work / "iterative-cache")]
    if request["runtime"]["device"] == "cpu":
        argv.append("--cpu")
    previous_argv = sys.argv
    try:
        sys.argv = argv
        # This is the upstream model execution, including exposure-embedding
        # interpolation, fixed HDR LoRA, ControlNet and actual denoising.
        controller._record_state(output, stage="checkpoint_inference", status="running",
                                 inference_started=True, inference_executed=None)
        inpaint.main()
        controller._record_state(output, stage="spherical_projection", status="running",
                                 inference_executed=True, inference_completed=True)
    finally:
        sys.argv = previous_argv
    envmaps = output / "envmap"
    envmaps.mkdir()
    projections = SimpleNamespace(ball_dir=str(inpaint_output / "square"), envmap_dir=str(envmaps), envmap_height=256, scale=4)
    exposures = {}
    for ev, text in ((0.0, "-00"), (-2.5, "-25"), (-5.0, "-50")):
        filename = "input_ev%s_seed%d.png" % (text, settings["seed"])
        for directory in ("raw", "square", "control"):
            path = inpaint_output / directory / filename
            with Image.open(path) as image:
                expected_size = (256, 256) if directory == "square" else (1024, 1024)
                if image.format != "PNG" or image.size != expected_size:
                    raise ValueError("DiffusionLight did not generate all three actual exposure/control outputs.")
                image.load()
        ball2envmap.process_image(projections, filename)
        if not (envmaps / filename).is_file():
            raise ValueError("The official DiffusionLight spherical projection did not produce an environment map.")
        exposures[ev] = filename
    merge = SimpleNamespace(input_dir=str(envmaps), output_dir=str(output), gamma=2.4, preview_output=False)
    controller._record_state(output, stage="exposure_merge", status="running")
    exposure2hdr.process_image(merge, {"name": "environment", "ev": exposures})
    controller._record_state(output, stage="hdr_validation", status="running")
    hdr = validate_hdr(output / "environment.exr")
    # A preview is explicitly a display transform, not an HDR master.
    import ezexr
    values = ezexr.imread(str(output / "environment.exr"))
    scale = max(float(np.percentile(values, 99)), 1e-8)
    preview = np.clip(values / scale, 0, 1) ** (1 / 2.4)
    Image.fromarray(np.round(preview * 255).astype(np.uint8), "RGB").save(output / "preview.png")
    # Remove aliases and duplicate checkpoint bytes before publishing inventory.
    controlnet_alias.unlink()
    shutil.rmtree(lora)
    # Log/state remain live evidence until the controller has reaped the worker;
    # their changing bytes must not enter the immutable artifact inventory.
    records = [artifact(path, output) for path in sorted(output.rglob("*"))
               if path.is_file() and path.name not in {"worker.log", "progress.json"}]
    provenance = {"schema": "cinematicum-diffusionlight-result", "version": 1, "inference_executed": True,
                  "engine": "DiffusionLight", "upstream_commit": lock["commit"], "device": request["runtime"]["device"],
                  "versions": versions, "settings": settings, "exposure_values": [0, -2.5, -5],
                  "lora_scale": 0.75, "merge_gamma": 2.4, "normalization": normalization,
                  "model_manifest_sha256": request["runtime"]["model_manifest_sha256"],
                  "models": {name: {k: v for k, v in entry.items() if k not in {"root", "path", "files"}}
                             for name, entry in models.items()}, "hdr": hdr, "artifacts": records,
                  "elapsed_seconds": time.monotonic() - started,
                  "scope": "Model-estimated relative lighting in the official sphere-projection convention. No absolute photometric calibration, HDR movie mastering, calibrated monitor or production-quality acceptance is claimed."}
    (output / "provenance.json").write_bytes(encoded(provenance))
    controller._record_state(output, stage="complete", status="succeeded", inference_executed=True)
    return {"available": True, "inference_executed": True, "environment": artifact(output / "environment.exr", output),
            "preview": artifact(output / "preview.png", output), "provenance": artifact(output / "provenance.json", output), "hdr": hdr}


def execute(request):
    if not isinstance(request, dict) or request.get("command") not in {"doctor", "infer"}:
        raise ValueError("Unknown fixed DiffusionLight worker command.")
    runtime = controller.validate_runtime(request.get("runtime"))
    with tempfile.TemporaryDirectory(prefix="cinematicum-diffusionlight-source-") as directory:
        snapshot = Path(directory)
        if request["command"] == "infer":
            controller._record_state(request["output_dir"], stage="source_verification", status="running")
        lock, source_records = source_snapshot(Path(runtime["upstream_root"]), snapshot)
        if request["command"] == "infer":
            controller._record_state(request["output_dir"], stage="model_verification", status="running")
        models = verify_models(runtime, lock)
        if request["command"] == "infer":
            controller._record_state(request["output_dir"], stage="runtime_imports", status="running")
        versions = runtime_versions(runtime["device"])
        sys.path.insert(0, str(snapshot))
        # Import the actual pipeline stages during doctor as well as infer.
        import inpaint
        import ball2envmap
        import exposure2hdr
        if request["command"] == "doctor":
            return {"available": True, "inference_verified": False, "versions": versions,
                    "device": runtime["device"], "upstream_commit": lock["commit"], "source_files": source_records,
                    "model_manifest_sha256": runtime["model_manifest_sha256"],
                    "scope": "Pinned local model/source identities and actual runtime imports; no checkpoint inference executed."}
        return infer({**request, "runtime": runtime}, snapshot, lock, models, versions)


def main():
    request = None
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("DiffusionLight worker request exceeds one megabyte.")
        # Upstream prints model progress to stdout. The worker protocol remains
        # one JSON result, with source diagnostics confined to stderr.
        with redirect_stdout(sys.stderr):
            request = json.loads(raw)
            result = execute(request)
        sys.stdout.buffer.write(encoded(result))
        return 0
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        if isinstance(request, dict) and request.get("command") == "infer":
            try:
                output = controller._path(request["output_dir"], True)
                if (output / "progress.json").is_file():
                    controller._record_state(output, status="failed", error=str(exc))
            except Exception:
                traceback.print_exc(file=sys.stderr)
        sys.stdout.buffer.write(encoded({"available": False, "inference_verified": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
