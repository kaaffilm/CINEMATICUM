"""Isolated NumPy/OCIO/OpenEXR float movie worker. JSON stdin, owned local files.

RGB is never clipped in the scene-linear compositor. Filtering and source-over
operate on associated float32 RGB; the sole display conversion is a derivative.
"""
from __future__ import annotations
from collections import OrderedDict
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from float_movie import DEFAULTS, FORMAT, LINEAR_SPACES, MAX_OUTPUT_BYTES, _verify_sources, validate_float_project
from imaging import _hash_file, _json_bytes, _owned
from image_worker import _modules, _config, _openexr, inspect_exr, decode_image, write_png16
from engine import _video_timing, track_state, validate_project
from timebase import project_rate


def color_processors(color, input_spaces):
    np, ocio, _ = _modules()
    config = _config(ocio, color["config"])
    for space in set(input_spaces) | {color["working_space"], color["output_space"]}:
        actual = config.getColorSpace(space)
        if actual is None or actual.isData():
            raise ValueError("Unknown or non-color OCIO input/output space: " + str(space))
    if color["view"] not in set(config.getViews(color["display"])) or color["view"] == "Raw":
        raise ValueError("The selected OCIO display view is not available.")
    inputs = {space: config.getProcessor(space, color["working_space"]) for space in set(input_spaces)}
    output = config.getProcessor(color["working_space"], color["output_space"])
    display = config.getProcessor(ocio.DisplayViewTransform(src=color["working_space"], display=color["display"], view=color["view"]))
    info = {**color, "ocio_version": ocio.__version__, "config_cache_id": config.getCacheID(),
            "config_sha256": hashlib.sha256(config.serialize().encode()).hexdigest(),
            "input_processors": {space: p.getCacheID() for space, p in inputs.items()},
            "output_processor": output.getCacheID(), "display_processor": display.getCacheID(),
            "display_encoding": "sRGB", "float_storage": "OpenEXR FLOAT32 RGBA, ZIP compression, associated alpha"}
    return config, {s: p.getDefaultCPUProcessor() for s, p in inputs.items()}, output.getDefaultCPUProcessor(), display.getDefaultCPUProcessor(), info


def doctor():
    np, ocio, _ = _modules(); exr = _openexr()
    config, _, _, _, info = color_processors(DEFAULTS, [DEFAULTS["default_input_space"]])
    return {"available": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")), "format": FORMAT,
            "versions": {"numpy": np.__version__, "OpenEXR": exr.__version__, "opencolorio": ocio.__version__},
            "color_spaces": [s for s in config.getColorSpaceNames() if not config.getColorSpace(s).isData()],
            "working_spaces": list(LINEAR_SPACES), "views": [v for v in config.getViews(DEFAULTS["display"]) if v != "Raw"],
            "defaults": DEFAULTS, "color": info}


def curve(clip, key, local_frame):
    values = {0: (clip[key], "linear")}
    values.update({k["frame"]: (k[key], k.get("interpolation", "linear")) for k in clip["keyframes"] if key in k})
    points = sorted(values.items()); frame = local_frame + clip.get("animation_offset", 0)
    if frame <= points[0][0]: return points[0][1][0]
    for (start, (a, mode)), (end, (b, _)) in zip(points, points[1:]):
        if frame < end:
            u = (frame - start) / (end - start)
            u = {"linear": lambda: u, "constant": lambda: 0, "ease_in": lambda: u*u,
                 "ease_out": lambda: 1-(1-u)*(1-u), "ease_in_out": lambda: u*u*(3-2*u)}[mode]()
            return a + (b-a)*u
    return points[-1][1][0]


def checked_pixels(rgba, np):
    if not np.isfinite(rgba).all() or np.max(np.abs(rgba[..., :3])) > 1e20:
        raise ValueError("Float movie contains nonfinite or unbounded RGB values.")
    if np.min(rgba[..., 3]) < 0 or np.max(rgba[..., 3]) > 1:
        raise ValueError("Float source alpha must be within 0–1.")
    return rgba


def read_float_exr(path, np):
    metadata = inspect_exr(path); exr = _openexr()
    with exr.File(str(path), separate_channels=True) as image:
        channels = image.channels()
        if any(c.pixels.dtype not in (np.dtype("float16"), np.dtype("float32")) for c in channels.values()):
            raise ValueError("Float movie EXR inputs require HALF or FLOAT color channels.")
        rgb = np.stack([channels[c].pixels for c in "RGB"], axis=-1).astype(np.float32)
        alpha = channels["A"].pixels.astype(np.float32) if "A" in channels else np.ones(rgb.shape[:2], dtype=np.float32)
    rgba = checked_pixels(np.dstack((rgb, alpha)), np)
    if metadata["alpha_mode"] == "premultiplied":
        np.divide(rgba[..., :3], alpha[..., None], out=rgba[..., :3], where=alpha[..., None] > 0)
        rgba[alpha == 0, :3] = 0
    return checked_pixels(rgba, np)


class Sources:
    def __init__(self, project, root, scratch, np):
        self.project, self.root, self.scratch, self.np = project, root, scratch, np
        self.assets = {a["id"]: a for a in project["assets"]}
        self.active = {}; self.stills = OrderedDict(); self.cached = 0

    def image(self, asset):
        np = self.np; key = asset["id"]
        if key in self.stills:
            self.stills.move_to_end(key); return self.stills[key].copy()
        source = _owned(self.root, asset["path"])
        rgba = read_float_exr(source, np) if source.suffix.lower() == ".exr" else decode_image(source, shutil.which("ffmpeg"), shutil.which("ffprobe"), np)[0]
        if rgba.shape != (asset["height"], asset["width"], 4):
            raise ValueError("Float still source dimensions changed.")
        while self.stills and self.cached + rgba.nbytes > 128 * 1024 ** 2:
            _, old = self.stills.popitem(last=False); self.cached -= old.nbytes
        if rgba.nbytes <= 128 * 1024 ** 2:
            self.stills[key] = rgba; self.cached += rgba.nbytes
        return rgba.copy()

    def frame(self, clip, local_frame, only_frame=False):
        asset = self.assets[clip["asset_id"]]
        if asset["kind"] == "image": return self.image(asset)
        np = self.np; ident = clip["id"]
        if ident not in self.active:
            floats = any(token in asset.get("pixel_format", "") for token in ("f32", "f16"))
            fmt = "gbrapf32le" if floats else "rgba64le"
            chain = _video_timing(clip, project_rate(self.project))
            if only_frame: chain += [f"select=eq(n\\,{local_frame})"]
            chain += ["format=" + fmt]
            log = (self.scratch / ("decode-" + ident + ".log")).open("wb")
            command = [shutil.which("ffmpeg"), "-v", "error", "-xerror", "-nostdin", "-threads", "1", "-filter_threads", "1",
                       "-protocol_whitelist", "file,pipe", "-i", str(_owned(self.root, asset["path"])),
                       "-map", "0:" + str(asset["video_stream_index"]), "-an", "-vf", ",".join(chain),
                       "-frames:v", "1" if only_frame else str(clip["duration"]), "-fps_mode", "passthrough",
                       "-threads", "1", "-f", "rawvideo", "-pix_fmt", fmt, "pipe:1"]
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log)
            self.active[ident] = (process, log, floats)
        process, log, floats = self.active[ident]
        size = asset["width"] * asset["height"] * (16 if floats else 8)
        data = bytearray()
        while len(data) < size:
            block = process.stdout.read(size-len(data))
            if not block: raise ValueError("A source ended before its selected float timeline frames.")
            data.extend(block)
        if floats:
            planes = np.frombuffer(data, dtype="<f4").reshape(4, asset["height"], asset["width"])
            rgba = np.stack([planes[2], planes[0], planes[1], planes[3]], axis=-1)
        else:
            rgba = np.frombuffer(data, dtype="<u2").reshape(asset["height"], asset["width"], 4).astype(np.float32) / np.float32(65535)
        if local_frame == clip["duration"] - 1 or only_frame:
            self.close(ident, expected=True)
        return checked_pixels(rgba, np)

    def close(self, ident, expected=False):
        process, log, _ = self.active.pop(ident)
        if expected:
            # The frame limiter must terminate naturally. No extra frame can be silently accepted.
            extra = process.stdout.read(1)
            if extra: raise ValueError("Float source decoder returned unexpected extra pictures.")
        process.stdout.close()
        if not expected and process.poll() is None: process.terminate()
        try: code = process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); code = process.wait(timeout=3)
        log.close()
        if expected and code: raise ValueError("A float source decoder failed after its selected frames.")

    def shutdown(self):
        for ident in list(self.active): self.close(ident)


def apply_input(rgba, processor, exposure, np):
    rgb = np.ascontiguousarray(rgba[..., :3], dtype=np.float32)
    processor.applyRGB(rgb)
    rgba[..., :3] = rgb * np.float32(2 ** exposure)
    return checked_pixels(rgba, np)


def place_over(canvas, rgba, x, y, scale, rotation, opacity, np):
    """Inverse bilinear sample of associated pixels, in bounded row tiles."""
    h, w = canvas.shape[:2]; sh, sw = rgba.shape[:2]
    fit = min(w/sw, h/sh) * scale
    angle = math.radians(rotation); cosine, sine = math.cos(angle), math.sin(angle)
    associated = rgba.copy(); associated[..., 3] *= np.float32(opacity); associated[..., :3] *= associated[..., 3:4]
    columns = np.arange(w, dtype=np.float64)[None, :] + .5 - w/2 - x*w
    for top in range(0, h, 64):
        rows = np.arange(top, min(top+64, h), dtype=np.float64)[:, None] + .5 - h/2 - y*h
        sx = (cosine*columns + sine*rows)/fit + sw/2 - .5
        sy = (-sine*columns + cosine*rows)/fit + sh/2 - .5
        ix = np.floor(sx).astype(np.int64); iy = np.floor(sy).astype(np.int64)
        fx = sx - ix; fy = sy - iy
        sampled = np.zeros((len(rows), w, 4), dtype=np.float32)
        for dx, dy, weight in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)):
            xx, yy = ix+dx, iy+dy
            valid = (xx >= 0) & (xx < sw) & (yy >= 0) & (yy < sh)
            values = associated[np.clip(yy, 0, sh-1), np.clip(xx, 0, sw-1)]
            sampled += values * (weight * valid).astype(np.float32)[..., None]
        destination = canvas[top:top+len(rows)]
        destination *= 1 - sampled[..., 3:4]
        destination += sampled


def straight_rgb(associated, np):
    rgb = np.zeros_like(associated[..., :3]); alpha = associated[..., 3:4]
    np.divide(associated[..., :3], alpha, out=rgb, where=alpha > 0)
    return np.ascontiguousarray(rgb)


def exr_write(filename, associated, color, frame, rate, np):
    exr = _openexr()
    header = {"compression": exr.ZIP_COMPRESSION, "type": exr.scanlineimage,
              "ocioColorSpace": color["output_space"], "ocioConfig": color["config"],
              "cinematicumAlpha": "premultiplied", "cinematicumFrame": frame,
              "cinematicumFrameRate": rate.ffmpeg, "comments": "CINEMATICUM scene-linear movie FLOAT32; see manifest.json."}
    if color["output_space"] == "ACEScg": header["chromaticities"] = (.713,.293,.165,.830,.128,.044,.32168,.33767)
    with exr.File(header, {"RGBA": np.ascontiguousarray(associated, dtype=np.float32)}) as image:
        image.write(str(filename))
    # Read the actual file and compare every stored FLOAT32 channel, not an encoder declaration.
    with exr.File(str(filename), separate_channels=True) as image:
        if any(image.channels()[c].pixels.dtype != np.dtype("float32") or not np.array_equal(image.channels()[c].pixels, associated[...,i]) for i,c in enumerate("RGBA")):
            raise ValueError("The EXR writer did not preserve the exact float32 pixels.")


def render(request):
    np, ocio, _ = _modules(); _openexr()
    root = Path(request["project_dir"]); output = Path(request["output_dir"])
    p = validate_float_project(validate_project(request["project"], root)); color = p["settings"]["float_color"]
    from float_movie import _duration
    frames = _duration(p); rate = project_rate(p); profile = request["profile"]; only = request.get("frame")
    sources = request["sources"]; _verify_sources(root, sources, None)
    spaces = [c.get("float_input_space", color["default_input_space"]) for c in p["clips"] if c["track"] >= 0]
    if p["titles"]: spaces += ["sRGB Encoded Rec.709 (sRGB)"]
    config, inputs, out_processor, display_processor, info = color_processors(color, spaces)
    (output / "config.ocio").write_text(config.serialize())
    if profile == "master32": (output / "frames").mkdir()
    readers = Sources(p, root, output, np)
    ordered = sorted(enumerate(p["clips"]), key=lambda item:(item[1]["track"],item[0]))
    encoder = None; encoder_log = None; count = 0; total_bytes = 0
    stats = {"minimum": None, "maximum": None, "negative_channels": 0, "above_one_channels": 0}
    try:
        if profile in {"preview", "h264", "prores"}:
            suffix = ".mov" if profile == "prores" else ".mp4"
            command = [shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-threads", "1", "-filter_threads", "1",
                       "-f", "rawvideo", "-pixel_format", "rgb48le", "-video_size", f"{p['width']}x{p['height']}",
                       "-framerate", rate.ffmpeg, "-i", "pipe:0", "-an", "-threads", "2"]
            command += ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"] if profile == "prores" else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
            command += ["-color_primaries", "bt709", "-color_trc", "iec61966-2-1", "-colorspace", "bt709", "-movie_timescale", "48000", str(output / ("display"+suffix))]
            encoder_log = (output / "encoder.log").open("wb")
            encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=encoder_log)
        for frame in ([only] if only is not None else range(frames)):
            canvas = np.zeros((p["height"], p["width"], 4), dtype=np.float32)
            if not p["settings"].get("transparent_background"): canvas[..., 3] = 1
            for _, clip in ordered:
                if clip["track"] < 0 or not track_state(p, clip["track"])[0] or not clip["start"] <= frame < clip["start"]+clip["duration"]: continue
                local = frame-clip["start"]
                rgba = readers.frame(clip, local, only_frame=only is not None)
                rgba = apply_input(rgba, inputs[clip.get("float_input_space",color["default_input_space"])], clip["grade"]["exposure"], np)
                values = [curve(clip,key,local) for key in ("x","y","scale","rotation","opacity")]
                place_over(canvas, rgba, *values, np)
            for title in p["titles"]:
                if not title["start"] <= frame < title["start"]+title["duration"]: continue
                rgba = readers.image(readers.assets[title["asset_id"]])
                rgba = apply_input(rgba, inputs["sRGB Encoded Rec.709 (sRGB)"], 0, np)
                local = frame-title["start"]; fade = title["fade"]
                opacity = min(1, local/fade, (title["duration"]-local)/fade) if fade else 1
                place_over(canvas, rgba, 0, 0, 1, 0, opacity, np)
            # Roundoff at alpha=1 is bounded independently of unbounded RGB values.
            if not np.isfinite(canvas).all() or np.min(canvas[...,3]) < -1e-6 or np.max(canvas[...,3]) > 1+1e-6:
                raise ValueError("Float composite produced invalid samples.")
            canvas[...,3] = np.clip(canvas[...,3],0,1)
            rgb = straight_rgb(canvas,np)
            if np.max(np.abs(rgb)) > 1e20: raise ValueError("Float composite exceeds its finite RGB bound.")
            minimum, maximum = float(rgb.min()), float(rgb.max())
            stats["minimum"] = minimum if stats["minimum"] is None else min(stats["minimum"],minimum)
            stats["maximum"] = maximum if stats["maximum"] is None else max(stats["maximum"],maximum)
            stats["negative_channels"] += int(np.count_nonzero(rgb<0)); stats["above_one_channels"] += int(np.count_nonzero(rgb>1))
            if profile == "master32":
                master = canvas.copy()
                if color["working_space"] != color["output_space"]:
                    transformed = rgb.copy(); out_processor.applyRGB(transformed); master[...,:3] = transformed * canvas[...,3:4]
                if not np.isfinite(master).all(): raise ValueError("The OCIO EXR output transform produced nonfinite pixels.")
                filename = output / "frames" / ("frame-%08d.exr" % frame)
                exr_write(filename,master,color,frame,rate,np)
                total_bytes += filename.stat().st_size
                if total_bytes > MAX_OUTPUT_BYTES: raise ValueError("Float EXR sequence exceeds 32 GiB.")
            # Composite black in scene-linear light before the nonlinear display transform.
            displayed = np.ascontiguousarray(canvas[...,:3]).copy(); display_processor.applyRGB(displayed)
            if not np.isfinite(displayed).all(): raise ValueError("The OCIO display transform produced nonfinite pixels.")
            if frame == 0 or only is not None:
                write_png16(output / "display.png", np.dstack((displayed,np.ones(displayed.shape[:2],dtype=np.float32))),np)
            if encoder:
                encoder.stdin.write(np.rint(np.clip(displayed,0,1)*65535).astype("<u2").tobytes())
            count += 1
            temporary = output / "progress.tmp"; temporary.write_bytes(_json_bytes({"progress":count/(1 if only is not None else frames)})); temporary.replace(output / "progress.json")
        if encoder:
            encoder.stdin.close()
            if encoder.wait(timeout=30): raise ValueError("Float display movie encoding failed.")
            encoder_log.close(); encoder_log=None; (output/"encoder.log").unlink()
        _verify_sources(root,sources,None)
        for file in output.glob("decode-*.log"): file.unlink()
        return {"format":FORMAT,"version":1,"frames":count,"processing_bits":32,"color":info,"linear_statistics":stats,
                "implementation":{name:_hash_file(Path(__file__).with_name(name))[0] for name in ("float_movie.py","float_movie_worker.py","engine.py","image_worker.py")},
                "rgb_clipped_in_compositor":False,"display_is_sdr":True,"hdr_monitoring":False,"calibrated_display":False,"issuance_effect":"NONE"}
    finally:
        readers.shutdown()
        if encoder and encoder.poll() is None:
            if encoder.stdin and not encoder.stdin.closed: encoder.stdin.close()
            encoder.terminate()
            try: encoder.wait(timeout=3)
            except subprocess.TimeoutExpired: encoder.kill(); encoder.wait(timeout=3)
        if encoder_log: encoder_log.close()


def main():
    try:
        data = sys.stdin.buffer.read(16*1024*1024+1)
        if len(data)>16*1024*1024: raise ValueError("Float movie request exceeds 16 MiB.")
        request=json.loads(data)
        if request.get("command")=="doctor": result=doctor()
        elif request.get("command")=="render": result=render(request)
        else: raise ValueError("Unknown float movie worker command.")
        sys.stdout.buffer.write(_json_bytes(result)); return 0
    except Exception as exc:
        sys.stdout.buffer.write(_json_bytes({"error":str(exc)[:6000],"type":type(exc).__name__})); return 1

if __name__ == "__main__": raise SystemExit(main())
