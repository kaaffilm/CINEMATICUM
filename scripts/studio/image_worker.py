"""Optional CINEMATICUM imaging worker: actual OCIO, LibRaw and float HDR.

JSON arrives on stdin from the local server. This process is launched in its
own process group and can be cancelled with its FFmpeg children. It never loads
external OCIO configurations, plugins, scripts, model weights or network media.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import zlib

# -I intentionally excludes the script directory. Add only this trusted module
# directory, never a path supplied by a project or the caller's environment.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from imaging import (ARTIFACT_NAMES, DEFAULT_CONFIG, DEFAULT_DISPLAY, MAX_PIXELS,
                     MAX_RAW_BYTES, MAX_SENSOR_PIXELS, _hash_file, _identity,
                     _json_bytes, _owned, validate_imaging_recipe)


def _modules(require_raw=False):
    try:
        import numpy as np
        import PyOpenColorIO as ocio
    except ImportError as exc:
        raise ValueError("The imaging runtime needs NumPy and OpenColorIO installed in its isolated environment.") from exc
    rawpy = None
    if require_raw:
        try:
            import rawpy
        except ImportError as exc:
            raise ValueError("RAW development needs rawpy/LibRaw in the isolated imaging environment.") from exc
    return np, ocio, rawpy


def _openexr():
    try:
        import OpenEXR
    except ImportError as exc:
        raise ValueError("Float imaging requires OpenEXR in the isolated imaging runtime.") from exc
    if not hasattr(OpenEXR, "File"):
        raise ValueError("The imaging runtime requires the supported OpenEXR.File API (OpenEXR 3.3 or newer).")
    return OpenEXR


def _registry(ocio):
    return [{"name": name, "label": label, "recommended": bool(recommended), "default": bool(default)}
            for name, label, recommended, default in ocio.BuiltinConfigRegistry().getBuiltinConfigs()]


def _config(ocio, name):
    if name not in {c["name"] for c in _registry(ocio)}:
        raise ValueError("Select a built-in OCIO configuration supplied by this imaging runtime. External configuration paths and URLs are not accepted.")
    config = ocio.Config.CreateFromBuiltinConfig(name)
    config.validate()
    if not config.getColorSpace("scene_linear") or not config.getColorSpace("lin_rec709"):
        raise ValueError("The selected builtin configuration lacks the required scene-linear and linear Rec.709 spaces.")
    return config


def doctor():
    result = {"available": False, "operations": [], "versions": {"python": sys.version.split()[0]}, "missing": []}
    for module, key in (("numpy", "numpy"), ("PyOpenColorIO", "opencolorio"), ("rawpy", "rawpy"), ("OpenEXR", "OpenEXR")):
        try:
            imported = __import__(module)
            result["versions"][key] = imported.__version__
            if key == "rawpy":
                result["versions"]["libraw"] = ".".join(map(str, imported.libraw_version))
        except ImportError:
            result["missing"].append(key)
    if not set(result["missing"]) & {"numpy", "opencolorio", "OpenEXR"}:
        _, ocio, _ = _modules()
        _openexr()
        result.update(available=True, operations=["ocio", "hdr_merge"], configs=_registry(ocio), default_config=DEFAULT_CONFIG)
        if "rawpy" not in result["missing"]:
            result["operations"].insert(1, "raw")
    if result["missing"]:
        result["reason"] = "Missing isolated runtime dependencies: " + ", ".join(result["missing"])
    return result


def catalog(name):
    _, ocio, _ = _modules()
    config = _config(ocio, name)
    views = [view for view in config.getViews(DEFAULT_DISPLAY) if view != "Raw"]
    if not views:
        raise ValueError("The builtin configuration has no supported sRGB display views.")
    return {"config": name, "configs": _registry(ocio), "cache_id": config.getCacheID(),
            "config_sha256": hashlib.sha256(config.serialize().encode("utf-8")).hexdigest(),
            "color_spaces": [{"name": space, "family": config.getColorSpace(space).getFamily(),
                              "encoding": config.getColorSpace(space).getEncoding()}
                             for space in config.getColorSpaceNames() if not config.getColorSpace(space).isData()],
            "roles": dict(config.getRoles()), "scene_linear": config.getRoleColorSpace("scene_linear"),
            "linear_rec709": config.getColorSpace("lin_rec709").getName(),
            "default_input_space": config.getColorSpace("srgb_texture").getName(),
            "displays": [{"name": DEFAULT_DISPLAY, "views": views}], "default_display": DEFAULT_DISPLAY,
            "default_view": next((view for view in views if view.startswith("ACES")), views[0]),
            "output": "16-bit sRGB display PNG and 32-bit scene-linear RGBA EXR"}


def _verified_input(root, descriptor):
    if not isinstance(descriptor, dict) or not isinstance(descriptor.get("path"), str):
        raise ValueError("The worker needs a project-owned input descriptor.")
    _identity(descriptor.get("sha256"), "Source hash", True)
    path = _owned(root, descriptor["path"])
    digest, size = _hash_file(path, 1024 * 1024 * 1024)
    if digest != descriptor["sha256"] or size != descriptor.get("size"):
        raise ValueError("An imaging input was altered after admission.")
    return path


def _raw_metadata(raw, rawpy):
    sizes = raw.sizes
    pattern = raw.raw_pattern
    return {"raw_width": sizes.raw_width, "raw_height": sizes.raw_height,
            "width": sizes.width, "height": sizes.height, "orientation": sizes.flip,
            "raw_type": raw.raw_type.name, "color_description": raw.color_desc.decode("ascii", errors="replace"),
            "cfa_pattern": pattern.tolist() if pattern is not None else None,
            "black_levels": [int(v) for v in raw.black_level_per_channel], "white_level": int(raw.white_level),
            "camera_white_balance": [float(v) for v in raw.camera_whitebalance],
            "daylight_white_balance": [float(v) for v in raw.daylight_whitebalance],
            "rawpy": rawpy.__version__, "libraw": ".".join(map(str, rawpy.libraw_version)),
            "exposure_metadata_available": False}


def _open_raw(path, rawpy):
    raw = rawpy.RawPy()
    try:
        with os.fdopen(os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as source:
            raw.open_buffer(source)
        sizes = raw.sizes
        if not 1 <= sizes.raw_width <= 16384 or not 1 <= sizes.raw_height <= 16384 or sizes.raw_width * sizes.raw_height > MAX_SENSOR_PIXELS:
            raise ValueError("The RAW sensor exceeds the 67-million-pixel processing bound.")
        raw.unpack()
        return raw
    except BaseException:
        raw.close()
        raise


def probe_raw(root, descriptor):
    _, _, rawpy = _modules(require_raw=True)
    path = _verified_input(root, descriptor)
    if descriptor["size"] > MAX_RAW_BYTES:
        raise ValueError("The camera RAW file exceeds 512 MiB.")
    with _open_raw(path, rawpy) as raw:
        return _raw_metadata(raw, rawpy)


def _checked_command(argv, payload=None, timeout=90):
    result = subprocess.run(argv, input=payload, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError("Image codec failed: " + result.stderr.decode("utf-8", errors="replace")[-1800:])
    return result.stdout


def decode_image(path, ffmpeg, ffprobe, np):
    """Decode straight-alpha RGB at float precision without transfer conversion."""
    if Path(path).suffix.lower() == ".exr":
        return read_exr(path, np)
    metadata = json.loads(_checked_command([ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
                                            "-select_streams", "v:0", "-show_entries",
                                            "stream=width,height,codec_name,pix_fmt", "-of", "json", str(path)]))
    streams = metadata.get("streams", [])
    if len(streams) != 1:
        raise ValueError("An imaging input needs one still-picture stream.")
    info = streams[0]
    width, height = info.get("width", 0), info.get("height", 0)
    if (not isinstance(width, int) or not isinstance(height, int) or not 1 <= width <= 16384 or
            not 1 <= height <= 16384 or width * height > MAX_PIXELS):
        raise ValueError("Imaging output is limited to 33.5 million pixels and 16,384 pixels per dimension.")
    if info.get("codec_name") not in {"png", "mjpeg", "webp", "tiff", "bmp", "exr"}:
        raise ValueError("Imaging accepts decoded PNG, JPEG, WebP, TIFF, BMP or EXR stills.")
    float_input = any(token in info.get("pix_fmt", "") for token in ("f32", "f16"))
    output_format = "gbrapf32le" if float_input else "rgba64le"
    data = _checked_command([ffmpeg, "-v", "error", "-nostdin", "-threads", "2", "-protocol_whitelist", "file,pipe",
                             "-noautorotate", "-i", str(path), "-frames:v", "1", "-threads", "2",
                             "-f", "rawvideo", "-pix_fmt", output_format, "pipe:1"])
    if len(data) != width * height * (16 if float_input else 8):
        raise ValueError("The image decoder returned incomplete float pixels.")
    if float_input:
        planar = np.frombuffer(data, dtype="<f4").reshape(4, height, width)
        rgba = np.stack((planar[2], planar[0], planar[1], planar[3]), axis=-1)
    else:
        # Preserve integer source precision before entering float. Older
        # swscale paths round packed RGB→planar float differently per channel.
        rgba = np.frombuffer(data, dtype="<u2").reshape(height, width, 4).astype(np.float32) / 65535
    if not np.isfinite(rgba).all() or np.max(np.abs(rgba[..., :3])) > 1e20:
        raise ValueError("The input image contains nonfinite or unbounded float pixels.")
    if np.min(rgba[..., 3]) < 0 or np.max(rgba[..., 3]) > 1:
        raise ValueError("Input alpha must stay in the 0–1 interval.")
    return rgba, info


def inspect_exr(path):
    """Check an EXR header before any pixel allocation."""
    exr = _openexr()
    with exr.File(str(path), header_only=True) as source:
        if len(source.parts) != 1:
            raise ValueError("Imaging EXR input must be a single-part RGB or RGBA image.")
        header = source.header()
        if header.get("type") not in {exr.scanlineimage, exr.tiledimage}:
            raise ValueError("Deep EXR input is not supported by this still-image operation.")
        lower, upper = header["dataWindow"]
        width, height = int(upper[0]) - int(lower[0]) + 1, int(upper[1]) - int(lower[1]) + 1
        display_lower, display_upper = header["displayWindow"]
        if (tuple(lower) != (0, 0) or tuple(display_lower) != tuple(lower) or tuple(display_upper) != tuple(upper)):
            raise ValueError("EXR data and display windows must match and start at zero.")
        if not 1 <= width <= 16384 or not 1 <= height <= 16384 or width * height > MAX_PIXELS:
            raise ValueError("The EXR exceeds the 33.5-million-pixel working image limit.")
        channels = header.get("channels", [])
        if {c.name for c in channels} not in ({"R", "G", "B"}, {"R", "G", "B", "A"}):
            raise ValueError("EXR input needs only full-resolution R, G, B and optional A channels.")
        if any(c.xSampling != 1 or c.ySampling != 1 for c in channels):
            raise ValueError("Subsampled EXR color channels are unsupported.")
        alpha_mode = header.get("cinematicumAlpha", "premultiplied")
        if alpha_mode not in {"straight", "premultiplied"}:
            raise ValueError("The EXR alpha interpretation is unsupported.")
        declared_space = header.get("ocioColorSpace")
        if not isinstance(declared_space, str) or not 1 <= len(declared_space) <= 240 or any(ord(c) < 32 for c in declared_space):
            declared_space = None
    return {"kind": "image", "width": width, "height": height, "color_space": declared_space,
            "alpha_mode": alpha_mode, "header_only": True, "reader": "OpenEXR.File"}


def read_exr(path, np):
    """Read bounded single-part RGB(A) EXR without a display/gamma conversion.

    Multi-part, deep, subsampled and cropped-window inputs need separate
    semantics and are explicitly rejected before pixel allocation.
    """
    metadata = inspect_exr(path)
    width, height, alpha_mode = metadata["width"], metadata["height"], metadata["alpha_mode"]
    exr = _openexr()
    with exr.File(str(path), separate_channels=True) as source:
        channels = source.channels()
        if any(c.pixels.dtype not in (np.dtype("float16"), np.dtype("float32")) for c in channels.values()):
            raise ValueError("Color EXR channels must be half or float, not unsigned integer data.")
        rgb = np.stack([channels[c].pixels for c in "RGB"], axis=-1).astype(np.float32)
        alpha = channels["A"].pixels.astype(np.float32) if "A" in channels else np.ones((height, width), dtype=np.float32)
    if (not np.isfinite(rgb).all() or not np.isfinite(alpha).all() or np.max(np.abs(rgb)) > 1e20
            or np.min(alpha) < 0 or np.max(alpha) > 1):
        raise ValueError("EXR pixels must be finite with bounded RGB and alpha in 0–1.")
    if alpha_mode == "premultiplied":
        np.divide(rgb, alpha[..., None], out=rgb, where=alpha[..., None] > 1e-8)
        rgb[alpha <= 1e-8] = 0
    return np.dstack((rgb, alpha)), {**metadata, "codec_name": "exr", "input_alpha": alpha_mode, "header_only": False}


def apply_ocio(rgb, config, source, destination, np):
    source_space, dest_space = config.getColorSpace(source), config.getColorSpace(destination)
    if source_space is None or dest_space is None or source_space.isData() or dest_space.isData():
        raise ValueError("Choose actual color spaces from the selected OCIO builtin configuration.")
    result = np.ascontiguousarray(rgb, dtype=np.float32)
    config.getProcessor(source_space.getName(), dest_space.getName()).getDefaultCPUProcessor().applyRGB(result)
    if not np.isfinite(result).all():
        raise ValueError("The OCIO transform produced nonfinite values. Check the source interpretation.")
    return result


def display_ocio(rgb, config, display, view, np, ocio):
    if display != DEFAULT_DISPLAY or view == "Raw" or view not in set(config.getViews(display)):
        raise ValueError("Choose a supported sRGB display view from the active configuration.")
    result = np.ascontiguousarray(rgb, dtype=np.float32).copy()
    transform = ocio.DisplayViewTransform(src=config.getRoleColorSpace("scene_linear"), display=display, view=view)
    processor = config.getProcessor(transform)
    processor.getDefaultCPUProcessor().applyRGB(result)
    if not np.isfinite(result).all():
        raise ValueError("The OCIO display processor produced nonfinite pixels.")
    return result, processor.getCacheID()


def decode_transfer(rgb, transfer, np):
    if transfer == "linear":
        return rgb
    if transfer == "srgb":
        return np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    if transfer == "rec709":
        return np.where(rgb < .081, rgb / 4.5, ((rgb + .099) / 1.099) ** (1 / .45))
    raise ValueError("Unsupported bracket transfer function.")


def merge_brackets(images, exposure_times, transfer, np, on_input=None):
    """Recover relative radiance from aligned, known-response, fixed-ISO brackets.

No response-curve fitting, alignment, optical flow or deghosting is implied.
The confidence is channel-wise triangular in the encoded capture interval;
clipped ends carry zero weight. Unrecoverable channels retain a documented
lower-bound/floor sample rather than being invented.
"""
    numerator = denominator = fallback = best_score = None
    all_dark = all_bright = None
    shape = None
    for index, (image, exposure) in enumerate(zip(images, exposure_times)):
        rgba = np.asarray(image, dtype=np.float32)
        if rgba.ndim != 3 or rgba.shape[-1] != 4 or shape is not None and rgba.shape != shape:
            raise ValueError("HDR brackets must have identical image dimensions.")
        shape = rgba.shape
        if not np.isfinite(rgba).all() or np.any(rgba[..., 3] < .99999):
            raise ValueError("HDR brackets must contain finite opaque photographs.")
        encoded = rgba[..., :3]
        if float(encoded.min()) < -.00001 or float(encoded.max()) > 1.00001:
            raise ValueError("Bracket inputs must be normalized capture values between zero and one.")
        encoded = np.clip(encoded, 0, 1)
        weights = np.minimum(encoded, 1 - encoded)
        dark, bright = encoded <= .002, encoded >= .998
        weights[dark | bright] = 0
        radiance = decode_transfer(encoded, transfer, np) / float(exposure)
        score = np.abs(encoded - .5)
        if numerator is None:
            numerator = np.zeros_like(radiance)
            denominator = np.zeros_like(radiance)
            fallback, best_score = radiance.copy(), score.copy()
            all_dark, all_bright = dark.copy(), bright.copy()
        else:
            better = score < best_score
            np.copyto(fallback, radiance, where=better)
            np.copyto(best_score, score, where=better)
            all_dark &= dark
            all_bright &= bright
        numerator += weights * radiance
        denominator += weights
        if on_input:
            on_input(index + 1)
    if numerator is None:
        raise ValueError("No HDR brackets were decoded.")
    unresolved = denominator <= 1e-12
    np.divide(numerator, denominator, out=numerator, where=~unresolved)
    np.copyto(numerator, fallback, where=unresolved)
    metrics = {"unrecovered_channels": int(np.count_nonzero(unresolved)),
               "unrecovered_pixels": int(np.count_nonzero(np.any(unresolved, axis=-1))),
               "all_dark_channels": int(np.count_nonzero(all_dark)),
               "all_saturated_channels": int(np.count_nonzero(all_bright)),
               "weighting": "triangular encoded RGB; excluded <=0.002 and >=0.998",
               "radiance_units": "relative linear Rec.709 signal per second",
               "assumptions": ["aligned static scene", "same aperture and ISO", "known input transfer", "no deghosting or fitted response curve"]}
    return numerator, metrics


def develop_raw(path, recipe, rawpy, np):
    with _open_raw(path, rawpy) as raw:
        metadata = _raw_metadata(raw, rawpy)
        scale = 2 if recipe["half_size"] else 1
        if math.ceil(raw.sizes.width / scale) * math.ceil(raw.sizes.height / scale) > MAX_PIXELS:
            raise ValueError("Full-size RAW output exceeds 33.5 million pixels. Enable half-size development.")
        algorithm = getattr(rawpy.DemosaicAlgorithm, recipe["demosaic"])
        if algorithm.isSupported is False:
            raise ValueError("This LibRaw build does not support the selected demosaic method.")
        mode = recipe["white_balance"]
        if mode == "camera" and not all(v > 0 for v in raw.camera_whitebalance[:3]):
            raise ValueError("This RAW source has no usable camera white balance. Choose daylight, auto or custom.")
        params = {"demosaic_algorithm": algorithm, "half_size": recipe["half_size"],
                  "use_camera_wb": mode == "camera", "use_auto_wb": mode == "auto",
                  "output_color": rawpy.ColorSpace.sRGB, "output_bps": 16, "gamma": (1, 1),
                  "no_auto_bright": True, "bright": 1, "no_auto_scale": False,
                  "highlight_mode": {"clip": rawpy.HighlightMode.Clip, "blend": rawpy.HighlightMode.Blend,
                                     "reconstruct": rawpy.HighlightMode.ReconstructDefault}[recipe["highlight"]]}
        if mode == "custom":
            params["user_wb"] = recipe["user_wb"]
        developed = raw.postprocess(**params)
    if developed.ndim != 3 or developed.shape[2] != 3 or developed.dtype != np.uint16:
        raise ValueError("LibRaw did not return the requested 16-bit linear RGB development.")
    height, width = developed.shape[:2]
    if width * height > MAX_PIXELS:
        raise ValueError("The developed RAW exceeds the working image limit.")
    rgb = developed.astype(np.float32) / 65535
    metadata.update(developed_width=width, developed_height=height,
                    development_encoding="linear Rec.709 / sRGB primaries",
                    development_precision="LibRaw 16-bit linear RGB promoted to float32",
                    output_gamma=[1, 1], auto_brightness=False,
                    raw_development_clipped_channels=int(np.count_nonzero(developed == 65535)))
    return rgb, metadata


def write_png16(path, rgba, np):
    """Original minimal RGBA16 PNG writer; sRGB values are already display-rendered."""
    if not np.isfinite(rgba).all():
        raise ValueError("Cannot write nonfinite display pixels.")
    height, width = rgba.shape[:2]
    pixels = np.rint(np.clip(rgba, 0, 1) * 65535).astype(">u2")
    def chunk(stream, tag, data):
        stream.write(struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    with Path(path).open("xb") as stream:
        stream.write(b"\x89PNG\r\n\x1a\n")
        chunk(stream, b"IHDR", struct.pack(">IIBBBBB", width, height, 16, 6, 0, 0, 0))
        chunk(stream, b"sRGB", b"\x00")
        compressor = zlib.compressobj(6)
        for row in pixels:
            data = compressor.compress(b"\x00" + row.tobytes())
            if data:
                chunk(stream, b"IDAT", data)
        tail = compressor.flush()
        if tail:
            chunk(stream, b"IDAT", tail)
        chunk(stream, b"IEND", b"")


def write_exr(path, rgba, scene_space, config_name, np):
    exr = _openexr()
    if Path(path).exists() or Path(path).is_symlink():
        raise ValueError("An EXR output must not overwrite an existing file.")
    associated = np.ascontiguousarray(rgba, dtype=np.float32).copy()
    associated[..., :3] *= associated[..., 3:4]
    header = {"compression": exr.ZIP_COMPRESSION, "type": exr.scanlineimage,
              "ocioColorSpace": scene_space, "ocioConfig": config_name,
              "cinematicumAlpha": "premultiplied", "comments": "Scene-linear CINEMATICUM imaging output; see the companion processing receipt."}
    if scene_space == "ACEScg":
        header["chromaticities"] = (.713, .293, .165, .830, .128, .044, .32168, .33767)
    with exr.File(header, {"RGBA": associated}) as target:
        target.write(str(path))


def _stats(rgb, np):
    if not np.isfinite(rgb).all():
        raise ValueError("The working image contains nonfinite pixels.")
    return {"min": float(rgb.min()), "max": float(rgb.max()), "mean": float(rgb.mean(dtype=np.float64)),
            "negative_channels": int(np.count_nonzero(rgb < 0)), "above_one_channels": int(np.count_nonzero(rgb > 1))}


def render(request):
    recipe = validate_imaging_recipe(request.get("recipe"))
    np, ocio, rawpy = _modules(require_raw=recipe["operation"] == "raw")
    root = Path(request["project_dir"]).absolute()
    scratch = Path(request["output_dir"]).absolute()
    relative = scratch.relative_to(root)
    if len(relative.parts) != 3 or relative.parts[:2] != ("imaging", "outputs") or not relative.name.startswith(".building-"):
        raise ValueError("The worker output is not a private project imaging directory.")
    _owned(root, relative, is_dir=True)
    ffmpeg, ffprobe = request["ffmpeg"], request["ffprobe"]
    for executable in (ffmpeg, ffprobe):
        if not isinstance(executable, str) or not Path(executable).is_absolute() or not os.access(executable, os.X_OK):
            raise ValueError("The worker requires resolved installed image codec executables.")
    inputs = request.get("inputs")
    expected = len(recipe["brackets"]) if recipe["operation"] == "hdr_merge" else 1
    if not isinstance(inputs, list) or len(inputs) != expected:
        raise ValueError("The imaging inputs do not match the recipe.")
    def progress(value):
        temporary = scratch / "progress.tmp"
        temporary.write_bytes(_json_bytes({"progress": value}))
        os.replace(str(temporary), str(scratch / "progress.json"))
    progress(.03)
    paths = []
    for index, descriptor in enumerate(inputs):
        source = _verified_input(root, descriptor)
        if recipe["operation"] == "raw":
            if descriptor.get("source_id") != recipe["source_id"] or descriptor["path"] != "imaging/sources/" + recipe["source_id"] + ".raw":
                raise ValueError("The RAW source does not match its immutable recipe reference.")
        else:
            expected_id = recipe["asset_id"] if recipe["operation"] == "ocio" else recipe["brackets"][index]["asset_id"]
            if not descriptor["path"].startswith("media/") or descriptor.get("asset_id") != expected_id:
                raise ValueError("Image inputs must match admitted project media references.")
        staging = scratch / ("source-%02d" % index + source.suffix)
        source_fd = os.open(str(source), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(source_fd, "rb") as inp, staging.open("xb") as out:
            shutil.copyfileobj(inp, out, 1024 * 1024)
        if _hash_file(staging) != (descriptor["sha256"], descriptor["size"]):
            raise ValueError("An input changed while snapshotting the imaging job.")
        paths.append(staging)
    config = _config(ocio, recipe["config"])
    scene_space = config.getRoleColorSpace("scene_linear")
    linear709 = config.getColorSpace("lin_rec709").getName()
    alpha, details = None, {}
    if recipe["operation"] == "ocio":
        rgba, details = decode_image(paths[0], ffmpeg, ffprobe, np)
        alpha = rgba[..., 3].copy()
        rgb = apply_ocio(rgba[..., :3], config, recipe["input_space"], scene_space, np)
        del rgba
    elif recipe["operation"] == "raw":
        rgb, details = develop_raw(paths[0], recipe, rawpy, np)
        rgb = apply_ocio(rgb, config, linear709, scene_space, np)
    else:
        order = sorted(range(len(paths)), key=lambda index: recipe["brackets"][index]["exposure_time"])
        times = [recipe["brackets"][index]["exposure_time"] for index in order]
        images = (decode_image(paths[index], ffmpeg, ffprobe, np)[0] for index in order)
        rgb, details = merge_brackets(images, times, recipe["input_transfer"], np,
                                      lambda count: progress(.1 + .4 * count / len(paths)))
        rgb = apply_ocio(rgb, config, linear709, scene_space, np)
    rgb *= 2.0 ** recipe["exposure"]
    linear_stats = _stats(rgb, np)
    height, width = rgb.shape[:2]
    if alpha is None:
        alpha = np.ones((height, width), dtype=np.float32)
    progress(.58)
    output = scratch / "result"
    output.mkdir()
    linear = np.dstack((rgb, alpha))
    write_exr(output / "linear.exr", linear, scene_space, recipe["config"], np)
    del linear
    progress(.77)
    displayed, processor_id = display_ocio(rgb, config, recipe["display"], recipe["view"], np, ocio)
    display_stats = _stats(displayed, np)
    del rgb
    write_png16(output / "display.png", np.dstack((displayed, alpha)), np)
    progress(.9)
    artifacts = {}
    for key, filename in (("linear", "linear.exr"), ("display", "display.png")):
        digest, size = _hash_file(output / filename)
        artifacts[key] = {"filename": filename, "sha256": digest, "size": size}
    versions = {"python": sys.version.split()[0], "numpy": np.__version__, "opencolorio": ocio.__version__,
                "OpenEXR": _openexr().__version__}
    if rawpy is not None:
        versions.update(rawpy=rawpy.__version__, libraw=".".join(map(str, rawpy.libraw_version)))
    receipt = {"version": 1, "operation": recipe["operation"], "recipe": recipe, "inputs": inputs,
               "width": width, "height": height, "linear_space": scene_space,
               "linear_encoding": "32-bit float RGBA EXR, premultiplied alpha, selected scene-linear space, exposure applied",
               "display_encoding": "16-bit sRGB RGBA PNG, straight alpha, OCIO display/view rendered and clipped to [0,1]",
               "config": {"name": recipe["config"], "source": "OCIO builtin registry",
                          "cache_id": config.getCacheID(),
                          "sha256": hashlib.sha256(config.serialize().encode("utf-8")).hexdigest()},
               "display_processor_cache_id": processor_id, "versions": versions,
               "source_details": details, "linear_statistics": linear_stats,
               "display_statistics_before_clipping": display_stats, "artifacts": artifacts,
               "created_at": time.time(), "issuance_effect": "NONE",
               "delivery_boundary": "The current movie compositor uses the SDR PNG. The EXR preserves scene-linear float data; this receipt does not certify HDR movie delivery."}
    (output / "receipt.json").write_bytes(_json_bytes(receipt))
    progress(.98)
    return {"ok": True, "width": width, "height": height}


def main():
    try:
        data = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Imaging requests exceed their size limit.")
        request = json.loads(data)
        if not isinstance(request, dict):
            raise ValueError("The imaging request must be an object.")
        command = request.get("command")
        if command == "doctor":
            result = doctor()
        elif command == "catalog":
            result = catalog(request.get("config", DEFAULT_CONFIG))
        elif command == "probe_raw":
            result = probe_raw(request["project_dir"], request["input"])
        elif command == "probe_exr":
            result = inspect_exr(_verified_input(request["project_dir"], request["input"]))
        elif command == "render":
            result = render(request)
        else:
            raise ValueError("Unsupported imaging command.")
        sys.stdout.buffer.write(_json_bytes(result))
        return 0
    except Exception as exc:
        sys.stdout.buffer.write(_json_bytes({"error": str(exc)[:6000], "type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
