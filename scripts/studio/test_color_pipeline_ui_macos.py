#!/usr/bin/env python3
"""Real WK LUT file import, apply, undo/redo and decoded paused-frame acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit
import zlib

from color_pipeline import load_lut, sample_lut
from server import Server, Store


def run(binary, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    screenshot = output / "ENGINE_TEST_color_pipeline_webkit.png"
    result = {"passed": False, "browser": "WKWebView", "fixture": "ENGINE TEST color pixels — not a film", "checks": {}}
    checks, started = result["checks"], time.monotonic()
    deadline = started + 17.5

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The color acceptance exceeded its 18-second budget")
        return min(maximum, remaining)

    with tempfile.TemporaryDirectory(prefix="cinematicum-color-webkit-TEST-") as temporary:
        work = Path(temporary)
        store = server = thread = project = None
        try:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg or not shutil.which("ffprobe"):
                raise RuntimeError("This media-backed color acceptance requires FFmpeg and ffprobe")
            source = work / "ENGINE_TEST_source.png"
            # Known RGB bytes, independent of any media generator/color matrix.
            rgb = (160, 80, 100)
            def chunk(kind, payload):
                return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
            payload = b"".join(b"\0" + bytes(rgb) * 160 for _ in range(90))
            source.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 160, 90, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(payload)) + chunk(b"IEND", b""))
            store = Store(work / "workspace")
            project = store.new_project({"name": "ENGINE TEST — Color pipeline", "fps": 12, "width": 160, "height": 90})
            asset = store.admit(project["id"], source, source.name)
            project = store.get(project["id"])
            project["clips"] = [{"id": "ENGINE_TEST_color", "asset_id": asset["id"], "track": 0, "start": 0, "in": 0, "duration": 12}]
            project = store.save(project["id"], project)
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            thread.start()
            native_timeout = budget(13.5, 3)
            process = subprocess.run([str(Path(binary).resolve()), "--url", "http://127.0.0.1:%d" % server.server_port,
                                      "--output", str(screenshot), "--script", str(Path(__file__).parent / "macos" / "ColorPipelineSmoke.js"),
                                      "--timeout", str(round(native_timeout, 2))], capture_output=True, text=True,
                                     timeout=budget(native_timeout + 2.2, .8))
            ui = None
            for line in reversed(process.stdout.splitlines()):
                try:
                    candidate = json.loads(line)
                    if isinstance(candidate, dict) and "passed" in candidate:
                        ui = candidate
                        break
                except ValueError:
                    pass
            if ui is None:
                raise RuntimeError("WebKit did not return a result: " + (process.stderr or process.stdout)[-2500:])
            result["ui"], result["helper_exit_code"] = ui, process.returncode
            if process.stderr.strip():
                result["helper_stderr_tail"] = process.stderr[-1800:]
            checks["native_color_ui_passed"] = ui.get("passed") is True and process.returncode == 0
            for step in ("reject_incomplete_cube_without_changing_clip", "import_domain_lut_and_apply_actual_rendered_pixels",
                         "one_change_undo_redo_and_explicit_camera_preset", "save_project_and_read_content_addressed_lut_descriptor"):
                checks[step] = step in ui.get("steps", [])
            saved = store.get(project["id"])
            clip = saved["clips"][0]
            p = clip.get("color_pipeline", {})
            reference = p.get("lut", {})
            checks["saved_clip_uses_verified_lut_and_selected_interpolation"] = reference == {"sha256": ui.get("sha256"), "interpolation": "trilinear"}
            checks["cancelled_camera_preset_did_not_modify_saved_input"] = p.get("input_transfer") == "rec709" and p.get("input_primaries") == "rec709"
            directory = store.project_dir(project["id"])
            lut = load_lut(directory, reference.get("sha256", ""))
            path = directory / "color" / "luts" / (lut.sha256 + ".cube")
            checks["project_cube_bytes_match_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest() == ui.get("sha256")
            checks["rejected_import_created_no_cube"] = len(list(path.parent.glob("*.cube"))) == 1
            checks["per_channel_nonzero_domain_preserved"] = lut.domain_min == (.25, -.5, .1) and lut.domain_max == (.75, 1.5, .6)
            expected = tuple(round(v * 255) for v in sample_lut(lut, [v / 255 for v in rgb], "trilinear"))
            checks["native_preview_pixel_matches_independent_domain_evaluation"] = all(abs(a - b) <= 4 for a, b in zip(ui.get("after_frame", {}).get("pixel", [])[:3], expected)) and len(ui.get("after_frame", {}).get("pixel", [])) == 4
            for stage in ("before_frame", "after_frame"):
                evidence = ui.get(stage, {})
                png_name = Path(unquote(urlsplit(evidence.get("url", "")).path)).name
                preview = directory / "previews" / png_name
                if not preview.is_file():
                    checks[stage + "_is_real_renderer_png"] = False
                    continue
                decoded = subprocess.run([ffmpeg, "-v", "error", "-threads", "1", "-i", str(preview), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-threads", "1", "pipe:1"],
                                         capture_output=True, check=True, timeout=budget(1, .2)).stdout
                pixel = tuple(decoded[(45 * 160 + 80) * 3:(45 * 160 + 80) * 3 + 3])
                checks[stage + "_is_real_renderer_png"] = len(pixel) == 3 and all(abs(a - b) <= 2 for a, b in zip(pixel, evidence.get("pixel", [])[:3]))
                if stage == "before_frame":
                    checks["unprocessed_input_matches_known_source"] = all(abs(a - b) <= 3 for a, b in zip(pixel, rgb))
                else:
                    checks["decoded_preview_matches_expected_transformed_rgb"] = all(abs(a - b) <= 4 for a, b in zip(pixel, expected))
                shutil.copy2(preview, output / ("ENGINE_TEST_color_" + stage + ".png"))
            shutil.copy2(path, output / "ENGINE_TEST_imported_color_lut.cube")
            checks["no_paid_generation_or_external_engine_job"] = all(job.get("kind") == "frame-preview" for job in store.jobs.values())
            checks["native_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            result["passed"] = all(checks.values())
            if not result["passed"]:
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(key for key, value in checks.items() if not value)
        except Exception as error:
            result["error"] = str(error)
        finally:
            if store and project:
                try:
                    (output / "ENGINE_TEST_color_saved_project.json").write_text(json.dumps(store.get(project["id"]), indent=2), encoding="utf-8")
                except Exception as error:
                    result["saved_evidence_error"] = str(error)
            if server:
                server.shutdown()
                server.server_close()
            if thread:
                thread.join(timeout=1)
            if store:
                store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["screenshot"] = str(screenshot) if screenshot.is_file() else None
    (output / "ENGINE_TEST_color_pipeline_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Actual macOS WKWebView is required; no browser acceptance was claimed."}))
        return 0
    if not args.binary or not args.binary.is_file():
        parser.error("Compile macos/SmokeTest.swift and supply its executable with --binary.")
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-color-webkit-TEST-evidence-"))
    result = run(args.binary, output)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
