"""Render the actual timeline graph at one frame for the authoring viewer.

The still uses the same project validation and compositor as movie delivery.
No third-party editor window, alternate shader approximation, or canned image
is involved. The caller may cancel an obsolete request without touching media.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from engine import _executable, _graph, RenderCancelled, validate_project


def preview_identity(project, frame):
    signature = {"pipeline": 9, "project": project, "frame": frame}
    return hashlib.sha256(json.dumps(signature, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def render_frame(project, project_dir, frame, output, cancel_event=None, timeout=45):
    p = validate_project(project, project_dir)
    duration = max([c["start"] + c["duration"] for c in p["clips"]] +
                   [t["start"] + t["duration"] for t in p["titles"]] + [0])
    if type(frame) is not int or not 0 <= frame < duration:
        raise ValueError("Preview frame must be inside the timeline.")
    if cancel_event is not None and cancel_event.is_set():
        raise RenderCancelled("Frame preview superseded")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Sound has no contribution to a still. Keeping its source decoders out of
    # this graph avoids unnecessary audio work while preserving picture timing.
    picture = copy.deepcopy(p)
    for clip in picture["clips"]:
        clip["volume"] = 0
        for key in clip.get("keyframes", []):
            key.pop("volume", None)
    with tempfile.TemporaryDirectory(prefix="cinematicum-frame-", dir=output.parent) as scratch:
        scratch = Path(scratch)
        inputs, graph, _ = _graph(picture, project_dir, scratch, cancel_event=cancel_event)
        graph += ";\n[aout]anullsink;\n[vout]trim=start_frame=%d:end_frame=%d,setpts=PTS-STARTPTS,format=rgb24[frameout]" % (frame, frame + 1)
        script = scratch / "graph.txt"
        script.write_text(graph)
        temporary = scratch / "frame.png"
        errors = scratch / "ffmpeg.log"
        command = [_executable("ffmpeg"), "-hide_banner", "-v", "error", "-nostdin", "-y",
                   "-filter_complex_threads", "1"] + inputs + [
                       "-filter_complex_script", str(script), "-map", "[frameout]",
                       "-frames:v", "1", "-threads", "1", "-c:v", "png", str(temporary)]
        with errors.open("wb") as log:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=log)
            began = time.monotonic()
            try:
                while process.poll() is None:
                    cancelled = cancel_event is not None and cancel_event.is_set()
                    if cancelled or time.monotonic() - began > timeout:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=3)
                        if cancelled:
                            raise RenderCancelled("Frame preview superseded")
                        raise RuntimeError("This frame exceeded the interactive preview time limit. Render the timeline to review it.")
                    time.sleep(.04)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
        if process.returncode or not temporary.is_file() or temporary.stat().st_size < 32:
            raise RuntimeError("Frame preview failed: " + errors.read_text(errors="replace")[-2500:])
        if cancel_event is not None and cancel_event.is_set():
            raise RenderCancelled("Frame preview superseded")
        if temporary.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("The frame renderer did not produce a PNG image.")
        os.replace(temporary, output)
    return {"frame": frame, "width": p["width"], "height": p["height"],
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "pipeline": "timeline-export-graph"}
