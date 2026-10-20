"""Real, optional media engines for CINEMATICUM Studio.

The caller supplies a configured ComfyUI URL, never a URL taken from a request.
Returned media must still pass the application's media probe before admission.
No remote provider is simulated and no global ComfyUI interrupt is issued.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


POSITIVE_MARKER = "CINEMATICUM_POSITIVE_PROMPT"
NEGATIVE_MARKER = "CINEMATICUM_NEGATIVE_PROMPT"
SEED_MARKER = "CINEMATICUM_SEED"
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024
_MAX_JSON_BYTES = 8 * 1024 * 1024
_HTTP_TIMEOUT = 15
_POLL_INTERVAL = 0.75
_COMFY_TIMEOUT = 1800
_BLENDER_TIMEOUT = 7200
_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}


class AdapterError(RuntimeError):
    """Engine refusal/failure, optionally retaining the accepted remote job ID."""

    def __init__(self, message, prompt_id=None):
        super().__init__(message)
        self.prompt_id = prompt_id


class AdapterCancelled(AdapterError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AdapterError("ComfyUI redirects are not accepted; configure its final server URL.")


def _base_url(url):
    if not isinstance(url, str):
        raise AdapterError("ComfyUI URL must be configured at server startup.")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise AdapterError("Invalid configured ComfyUI URL.") from exc
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or any(ord(c) < 32 for c in url)):
        raise AdapterError("ComfyUI URL must be an HTTP(S) server URL without credentials, query, or fragment.")
    if port is not None and not 1 <= port <= 65535:
        raise AdapterError("Invalid ComfyUI server port.")
    return url.rstrip("/")


def _opener():
    # Do not send local engine traffic through ambient proxy configuration.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _json_request(base, route, payload=None, timeout=_HTTP_TIMEOUT):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
    request = urllib.request.Request(
        base + route, data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json",
                 "User-Agent": "CINEMATICUM-Studio/1"},
        method="GET" if payload is None else "POST",
    )
    try:
        with _opener().open(request, timeout=timeout) as response:
            raw = response.read(_MAX_JSON_BYTES + 1)
        if len(raw) > _MAX_JSON_BYTES:
            raise AdapterError("ComfyUI returned an oversized JSON response.")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise AdapterError("ComfyUI returned a non-object JSON response.")
        return result
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            error = json.loads(exc.read(8192)).get("error", {})
            if isinstance(error, dict):
                detail = str(error.get("message", error.get("type", "")))[:500]
            elif isinstance(error, str):
                detail = error[:500]
        except (ValueError, AttributeError, OSError):
            pass
        raise AdapterError("ComfyUI HTTP %s%s" % (exc.code, ": " + detail if detail else "")) from exc
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        raise AdapterError("ComfyUI connection failed: %s" % str(exc)[:500]) from exc
    except (ValueError, UnicodeError) as exc:
        raise AdapterError("ComfyUI returned invalid JSON.") from exc


def check_comfyui(url):
    """Read-only connectivity check; does not submit or purchase a generation."""
    try:
        base = _base_url(url)
        stats = _json_request(base, "/system_stats", timeout=3)
        if not isinstance(stats.get("system"), dict) or not isinstance(stats.get("devices"), list):
            raise AdapterError("The configured server did not return ComfyUI system statistics.")
        return {"available": True, "reason": "ComfyUI responded; a compatible API workflow and models are still required."}
    except AdapterError as exc:
        return {"available": False, "reason": str(exc)}


def validate_workflow(graph):
    """Validate API-export shape and return an independent copy without rebinding."""
    if not isinstance(graph, dict) or not graph:
        raise AdapterError("Provide a nonempty ComfyUI API-export workflow object.")
    if "nodes" in graph:
        raise AdapterError("This is a ComfyUI UI workflow; export it in API format first.")
    if len(graph) > 2000:
        raise AdapterError("ComfyUI workflow exceeds the 2,000-node limit.")
    for node_id, node in graph.items():
        if not isinstance(node_id, str) or not node_id or len(node_id) > 200:
            raise AdapterError("ComfyUI API node IDs must be nonempty strings.")
        if (not isinstance(node, dict) or not isinstance(node.get("class_type"), str)
                or not node["class_type"].strip() or not isinstance(node.get("inputs"), dict)):
            raise AdapterError("Each API workflow node needs a class_type and an inputs object.")
    try:
        encoded = json.dumps(graph, allow_nan=False)
        if len(encoded.encode("utf-8")) > 4 * 1024 * 1024:
            raise AdapterError("ComfyUI workflow exceeds 4 MiB.")
        return json.loads(encoded)
    except (TypeError, ValueError, RecursionError) as exc:
        raise AdapterError("ComfyUI workflow must contain finite JSON values.") from exc


def _bind_workflow(graph, prompt, negative, seed):
    result = validate_workflow(graph)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 32768:
        raise AdapterError("A nonempty generation prompt of at most 32,768 characters is required.")
    if not isinstance(negative, str) or len(negative) > 32768:
        raise AdapterError("Negative prompt must be text of at most 32,768 characters.")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2 ** 64:
        raise AdapterError("Seed must be an integer between 0 and 2^64 - 1.")
    count = {"positive": 0, "negative": 0, "seed": 0}

    def bind(value):
        if isinstance(value, dict):
            return {key: bind(item) for key, item in value.items()}
        if isinstance(value, list):
            return [bind(item) for item in value]
        if not isinstance(value, str):
            return value
        if value == SEED_MARKER:
            count["seed"] += 1
            return seed
        if SEED_MARKER in value:
            raise AdapterError("CINEMATICUM_SEED must be the entire input value, so it can become an integer.")
        # One pass is important: marker-like text in the user's prompt must stay text.
        tokens = (POSITIVE_MARKER, NEGATIVE_MARKER)
        pieces = []
        cursor = 0
        while cursor < len(value):
            matches = [(value.find(token, cursor), token) for token in tokens]
            matches = [(index, token) for index, token in matches if index >= 0]
            if not matches:
                pieces.append(value[cursor:])
                break
            index, token = min(matches)
            pieces.append(value[cursor:index])
            pieces.append(prompt if token == POSITIVE_MARKER else negative)
            count["positive" if token == POSITIVE_MARKER else "negative"] += 1
            cursor = index + len(token)
        return "".join(pieces)

    for node in result.values():
        node["inputs"] = bind(node["inputs"])
    if not count["positive"]:
        raise AdapterError("API workflow must contain CINEMATICUM_POSITIVE_PROMPT in an input; arbitrary text nodes are never overwritten.")
    return result, count


def _cancelled(event, prompt_id=None):
    if event is not None and event.is_set():
        message = "Operation cancelled."
        if prompt_id:
            message = ("Stopped waiting for ComfyUI prompt %s. It may still run on the shared server; "
                       "no global interrupt was sent." % prompt_id)
        raise AdapterCancelled(message, prompt_id=prompt_id)


def _video_candidates(outputs):
    candidates = []

    def visit(value, node_id):
        if isinstance(value, list):
            for item in value:
                visit(item, node_id)
        elif isinstance(value, dict):
            name = value.get("filename")
            if isinstance(name, str) and Path(name).suffix.lower() in _VIDEO_EXTENSIONS:
                subfolder = value.get("subfolder", "")
                kind = value.get("type", "output")
                if (not name or "/" in name or "\\" in name or any(ord(c) < 32 for c in name)
                        or not isinstance(subfolder, str) or "\\" in subfolder
                        or PurePosixPath(subfolder).is_absolute()
                        or ".." in PurePosixPath(subfolder).parts
                        or any(ord(c) < 32 for c in subfolder) or kind not in ("output", "temp")):
                    raise AdapterError("ComfyUI returned an unsafe video output descriptor.")
                candidates.append({"filename": name, "subfolder": subfolder, "type": kind,
                                   "node_id": node_id})
            for item in value.values():
                if isinstance(item, (list, dict)):
                    visit(item, node_id)

    if isinstance(outputs, dict):
        for node_id, value in outputs.items():
            visit(value, node_id)
    # Prefer delivery-friendly MP4, while retaining deterministic ordering.
    return sorted(candidates, key=lambda item: ({".mp4": 0, ".webm": 1, ".mov": 2}[Path(item["filename"]).suffix.lower()],
                                               str(item["node_id"]), item["filename"]))


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download_video(base, candidate, directory, deadline, event, prompt_id):
    suffix = Path(candidate["filename"]).suffix.lower()
    final = directory / ("comfyui-" + uuid.uuid4().hex + suffix)
    part = final.with_suffix(final.suffix + ".part")
    query = urllib.parse.urlencode({key: candidate[key] for key in ("filename", "subfolder", "type")})
    request = urllib.request.Request(base + "/view?" + query, headers={"User-Agent": "CINEMATICUM-Studio/1"})
    try:
        with _opener().open(request, timeout=_HTTP_TIMEOUT) as response, part.open("xb") as target:
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) > MAX_DOWNLOAD_BYTES:
                raise AdapterError("ComfyUI video exceeds the 2 GiB download limit.", prompt_id)
            size = 0
            while True:
                _cancelled(event, prompt_id)
                if time.monotonic() >= deadline:
                    raise AdapterError("ComfyUI video download timed out.", prompt_id)
                # read1 returns available bytes instead of waiting to fill the
                # whole block, so a slow stream cannot hide the total deadline.
                block = getattr(response, "read1", response.read)(64 * 1024)
                if not block:
                    break
                size += len(block)
                if size > MAX_DOWNLOAD_BYTES:
                    raise AdapterError("ComfyUI video exceeds the 2 GiB download limit.", prompt_id)
                target.write(block)
            if not size:
                raise AdapterError("ComfyUI returned an empty video file.", prompt_id)
            if declared is not None and size != int(declared):
                raise AdapterError("ComfyUI video download was incomplete.", prompt_id)
            target.flush()
            os.fsync(target.fileno())
        _cancelled(event, prompt_id)
        os.replace(str(part), str(final))
        return final
    except AdapterError:
        raise
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as exc:
        raise AdapterError("Cannot download output for ComfyUI prompt %s: %s" % (prompt_id, str(exc)[:400]), prompt_id) from exc
    finally:
        if part.exists():
            part.unlink()


def generate_comfyui(url, workflow, prompt, negative, seed, output_dir,
                     progress=lambda value: None, cancel_event=None):
    """Submit exactly once; wait for verified job completion and download a video.

    Cancellation is local: it never interrupts another user's shared-server job.
    An ambiguous submission error is not retried. The caller probes the returned
    media before admitting it into its project.
    """
    _cancelled(cancel_event)
    base = _base_url(url)
    graph, bindings = _bind_workflow(workflow, prompt, negative, seed)
    graph_hash = hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    progress(0.0)
    deadline = time.monotonic() + _COMFY_TIMEOUT
    try:
        accepted = _json_request(base, "/prompt", {"prompt": graph, "client_id": uuid.uuid4().hex})
    except AdapterError as exc:
        raise AdapterError("ComfyUI submission failed or is uncertain; it was not retried. %s" % exc) from exc
    prompt_id = accepted.get("prompt_id")
    if accepted.get("error") or accepted.get("node_errors") or not isinstance(prompt_id, str) or not prompt_id:
        raise AdapterError("ComfyUI rejected the workflow: %s" % str(accepted.get("error", accepted.get("node_errors", "missing prompt_id")))[:800])
    if len(prompt_id) > 256:
        raise AdapterError("ComfyUI returned an invalid prompt ID.")
    progress(0.1)
    try:
        while time.monotonic() < deadline:
            _cancelled(cancel_event, prompt_id)
            history = _json_request(base, "/history/" + urllib.parse.quote(prompt_id, safe=""))
            result = history.get(prompt_id)
            if isinstance(result, dict):
                status = result.get("status", {})
                if not isinstance(status, dict):
                    raise AdapterError("ComfyUI returned invalid prompt status.", prompt_id)
                messages = status.get("messages", [])
                failed = status.get("status_str") in ("error", "failed", "cancelled")
                detail = ""
                for message in messages if isinstance(messages, list) else []:
                    if isinstance(message, list) and message and message[0] in ("execution_error", "execution_interrupted"):
                        failed = True
                        if len(message) > 1 and isinstance(message[1], dict):
                            detail = str(message[1].get("exception_message", message[0]))[:500]
                if failed:
                    raise AdapterError("ComfyUI prompt %s failed%s" % (prompt_id, ": " + detail if detail else "."), prompt_id)
                if status.get("completed") is True or status.get("status_str") == "success":
                    candidates = _video_candidates(result.get("outputs", {}))
                    if not candidates:
                        raise AdapterError("ComfyUI prompt %s completed without an MP4, WebM, or MOV output. Image-only workflows cannot supply a film shot." % prompt_id, prompt_id)
                    progress(0.8)
                    candidate = candidates[0]
                    output = _download_video(base, candidate, directory, deadline, cancel_event, prompt_id)
                    progress(1.0)
                    return {"path": str(output), "provenance": {
                        "backend": "comfyui", "prompt_id": prompt_id, "workflow_sha256": graph_hash,
                        "requested_seed": seed, "seed_bound": bool(bindings["seed"]),
                        "marker_bindings": bindings, "output_node": candidate["node_id"],
                        "server_filename": candidate["filename"], "output_sha256": _sha256(output),
                    }}
            if cancel_event is not None:
                cancel_event.wait(_POLL_INTERVAL)
            else:
                time.sleep(_POLL_INTERVAL)
        raise AdapterError("Timed out waiting for ComfyUI prompt %s; it may still be running. It was not resubmitted." % prompt_id, prompt_id)
    except AdapterError as exc:
        if exc.prompt_id is None:
            exc.prompt_id = prompt_id
        raise


def find_blender():
    executable = shutil.which("blender")
    if executable:
        return executable
    candidate = "/Applications/Blender.app/Contents/MacOS/Blender"
    return candidate if os.path.isfile(candidate) and os.access(candidate, os.X_OK) else None


def _terminate_owned(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=3)
    except ProcessLookupError:
        pass


def _run_owned(argv, log_path, event, timeout, on_tick=lambda: None):
    """Only signal a process group created by this invocation, never an existing PID."""
    _cancelled(event)
    with Path(log_path).open("wb") as log:
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as exc:
            raise AdapterError("Cannot start media engine: %s" % exc) from exc
        started = time.monotonic()
        try:
            while process.poll() is None:
                _cancelled(event)
                if time.monotonic() - started > timeout:
                    raise AdapterError("Media engine exceeded its execution time limit.")
                on_tick()
                if event is not None:
                    event.wait(0.15)
                else:
                    time.sleep(0.15)
            _cancelled(event)
            if process.returncode:
                log.flush()
                with Path(log_path).open("rb") as source:
                    source.seek(max(0, source.seek(0, os.SEEK_END) - 2400))
                    detail = source.read().decode("utf-8", errors="replace")
                raise AdapterError("%s exited with code %s: %s" % (Path(argv[0]).name, process.returncode, detail))
        finally:
            _terminate_owned(process)


def render_blender(scene_path, output_dir, frame_start, frame_end, fps=24,
                   progress=lambda value: None, cancel_event=None):
    """Render an explicitly imported .blend through Blender and encode a real MP4.

    Auto-execution from the scene is disabled. Only our generated settings script
    is run. Frame bounds are inclusive, matching Blender's animation renderer.
    """
    _cancelled(cancel_event)
    executable = find_blender()
    ffmpeg = shutil.which("ffmpeg")
    if not executable:
        raise AdapterError("Blender is not installed or is not executable.")
    if not ffmpeg:
        raise AdapterError("FFmpeg is required to encode the Blender image sequence.")
    try:
        scene = Path(scene_path).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AdapterError("The imported Blender scene is missing.") from exc
    if not scene.is_file() or scene.suffix.lower() != ".blend":
        raise AdapterError("Choose an imported .blend scene.")
    if (isinstance(frame_start, bool) or isinstance(frame_end, bool)
            or not isinstance(frame_start, int) or not isinstance(frame_end, int)
            or not 0 <= frame_start <= frame_end <= 1000000):
        raise AdapterError("Blender frame bounds must be integers with 0 <= start <= end <= 1,000,000.")
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 1 <= fps <= 240:
        raise AdapterError("Blender delivery frame rate must be between 1 and 240.")
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    scene_hash = _sha256(scene)
    final = directory / ("blender-" + uuid.uuid4().hex + ".mp4")
    progress(0.0)
    with tempfile.TemporaryDirectory(prefix=".blender-", dir=str(directory)) as temporary:
        work = Path(temporary)
        frames = work / "frames"
        frames.mkdir()
        disabled_outputs = work / "disabled-compositor-outputs"
        disabled_outputs.mkdir()
        script = work / "render_scene.py"
        script.write_text(
            "import bpy\n"
            "# File Output nodes write independently of scene.render.filepath.\n"
            "# Disable their side effects without disabling the main composite.\n"
            "# This is an output safeguard, not an operating-system sandbox.\n"
            "safe_output_directory = %r\n" % str(disabled_outputs)
            + "pending_trees = list(bpy.data.node_groups)\n"
            "for candidate_scene in bpy.data.scenes:\n"
            "    for property_name in ('node_tree', 'compositing_node_group'):\n"
            "        candidate_tree = getattr(candidate_scene, property_name, None)\n"
            "        if candidate_tree is not None:\n"
            "            pending_trees.append(candidate_tree)\n"
            "seen_trees = set()\n"
            "output_index = 0\n"
            "while pending_trees:\n"
            "    tree = pending_trees.pop()\n"
            "    tree_key = tree.as_pointer()\n"
            "    if tree_key in seen_trees:\n"
            "        continue\n"
            "    seen_trees.add(tree_key)\n"
            "    for node in tree.nodes:\n"
            "        nested_tree = getattr(node, 'node_tree', None)\n"
            "        if nested_tree is not None:\n"
            "            pending_trees.append(nested_tree)\n"
            "        if node.bl_idname != 'CompositorNodeOutputFile':\n"
            "            continue\n"
            "        node.mute = True\n"
            "        output_index += 1\n"
            "        for property_name in ('base_path', 'directory'):\n"
            "            if hasattr(node, property_name):\n"
            "                setattr(node, property_name, safe_output_directory)\n"
            "        if hasattr(node, 'file_name'):\n"
            "            node.file_name = 'disabled_output_%04d' % output_index\n"
            "        for collection_name in ('file_slots', 'layer_slots', 'file_output_items'):\n"
            "            for slot_index, slot in enumerate(getattr(node, collection_name, ())):\n"
            "                if hasattr(slot, 'path'):\n"
            "                    slot.path = 'slot_%04d' % slot_index\n"
            "                elif hasattr(slot, 'name'):\n"
            "                    slot.name = 'slot_%04d' % slot_index\n"
            "scene = bpy.context.scene\n"
            + "scene.frame_start = %r\nscene.frame_end = %r\nscene.frame_step = 1\n" % (frame_start, frame_end)
            + "scene.render.fps = %r\nscene.render.fps_base = %r\n" % (round(fps), round(fps) / fps)
            + "scene.render.image_settings.file_format = 'PNG'\n"
            "scene.render.image_settings.color_mode = 'RGBA'\n"
            "scene.render.image_settings.color_depth = '16'\n"
            "scene.render.use_file_extension = True\n"
            "scene.render.use_multiview = False\n"
            "scene.render.filepath = %r\n" % str(frames / "frame_######")
            + "bpy.ops.render.render(animation=True)\n",
            encoding="utf-8",
        )
        total = frame_end - frame_start + 1
        previous = [-1]

        def report_frames():
            count = len(list(frames.glob("frame_*.png")))
            if count != previous[0]:
                previous[0] = count
                progress(min(0.85, 0.85 * count / total))

        _run_owned([executable, "--background", "--factory-startup", "--disable-autoexec", str(scene),
                    "--python-exit-code", "1", "--python", str(script)],
                   work / "blender.log", cancel_event, _BLENDER_TIMEOUT, report_frames)
        for frame in range(frame_start, frame_end + 1):
            expected = frames / ("frame_%06d.png" % frame)
            if not expected.is_file() or expected.stat().st_size == 0:
                raise AdapterError("Blender did not produce requested frame %d." % frame)
        _cancelled(cancel_event)
        progress(0.86)
        encoded = work / "encoded.mp4"
        _run_owned([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-n",
                    "-framerate", str(fps), "-start_number", str(frame_start),
                    "-i", str(frames / "frame_%06d.png"), "-frames:v", str(total),
                    "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(encoded)],
                   work / "encode.log", cancel_event, _BLENDER_TIMEOUT)
        if not encoded.is_file() or encoded.stat().st_size == 0:
            raise AdapterError("Blender encoding completed without a nonempty video.")
        _cancelled(cancel_event)
        os.replace(str(encoded), str(final))
    progress(1.0)
    return {"path": str(final), "provenance": {"backend": "blender", "scene_sha256": scene_hash,
            "frame_start": frame_start, "frame_end": frame_end, "frame_end_inclusive": True,
            "fps": fps, "output_sha256": _sha256(final), "autoexec_enabled": False,
            "compositor_file_outputs_muted": True}}
