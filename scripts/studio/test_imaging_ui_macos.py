#!/usr/bin/env python3
"""Native image development acceptance, each invocation stays below 20 seconds.

Run OCIO, HDR and genuine RAW as separate invocations. The optional camera
fixture is served only by this test's guarded loopback handler, then chosen
through the shipped file input. No fixture bytes are bundled with the app.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit

from engine import render_project
from imaging import find_imaging_python, imaging_capabilities
from server import Handler, Server, Store
from test_imaging import png16, read_generated_png16


def run(binary, output, operation="ocio", raw_file=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    screenshot = output / ("ENGINE_TEST_imaging_" + operation + "_webkit.png")
    result = {"passed": False, "operation": operation, "browser": "WKWebView",
              "fixture": "ENGINE TEST imaging acceptance — not a film", "checks": {}}
    checks, started = result["checks"], time.monotonic()
    deadline = started + 18

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The imaging acceptance exceeded its 18-second execution budget")
        return min(maximum, remaining)

    with tempfile.TemporaryDirectory(prefix="cinematicum-imaging-webkit-TEST-") as temporary:
        work = Path(temporary)
        store = server = thread = project = None
        try:
            runtime = imaging_capabilities()
            if not runtime["available"] or operation not in runtime["operations"]:
                raise RuntimeError(runtime.get("reason", "The actual imaging runtime is unavailable"))
            if operation == "raw" and (not raw_file or not Path(raw_file).is_file()):
                raise ValueError("Genuine RAW acceptance requires --raw-file with a real camera fixture")
            store = Store(work / "workspace")
            project = store.new_project({"name": "ENGINE TEST — Image development " + operation, "fps": 12, "width": 160, "height": 90})
            fixture = {"operation": operation}
            if operation == "hdr_merge":
                fixture["brackets"] = []
                for index, shutter in enumerate((.025, .1, .4)):
                    values = []
                    for radiance in (.12, 2., 10.):
                        value = min(1, radiance * shutter)
                        values.append(12.92 * value if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055)
                    source = work / ("ENGINE_TEST_bracket_%d.png" % index)
                    png16(source, values, 160, 90)
                    asset = store.admit(project["id"], source, source.name)
                    fixture["brackets"].append({"asset_id": asset["id"], "exposure_time": shutter})
            elif operation == "ocio":
                source = work / "ENGINE_TEST_color_source.png"
                png16(source, (.25, .5, .75), 160, 90)
                asset = store.admit(project["id"], source, source.name)
                fixture["asset_id"] = asset["id"]
            else:
                raw_file = Path(raw_file).resolve()
                fixture["raw_name"] = raw_file.name
                result["camera_fixture"] = {"name": raw_file.name, "sha256": hashlib.sha256(raw_file.read_bytes()).hexdigest(), "size": raw_file.stat().st_size}
            script = work / "ImagingSmoke.js"
            source_script = (Path(__file__).parent / "macos/ImagingSmoke.js").read_text()
            script.write_text(source_script.replace("/* ENGINE_TEST_CONFIG */ {}", json.dumps(fixture)), encoding="utf-8")
            class FixtureHandler(Handler):
                def do_GET(self):
                    if self.path == "/__engine_test__/camera-raw" and operation == "raw":
                        try:
                            self.guard()
                            return self.file(raw_file)
                        except Exception as exc:
                            return self.json(400, {"error": str(exc)})
                    return super().do_GET()
            server = Server(0, store)
            server.RequestHandlerClass = FixtureHandler
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            thread.start()
            native_timeout = budget(14.2, 2.5)
            process = subprocess.run([str(Path(binary).resolve()), "--url", "http://127.0.0.1:%d" % server.server_port,
                                      "--output", str(screenshot), "--script", str(script), "--timeout", str(round(native_timeout, 2))],
                                     capture_output=True, text=True, timeout=budget(native_timeout + 1.5, 1))
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
                raise RuntimeError("WebKit did not return imaging evidence: " + (process.stderr or process.stdout)[-2000:])
            result["ui"], result["helper_exit_code"] = ui, process.returncode
            checks["native_development_controls_passed"] = ui.get("passed") is True and process.returncode == 0
            if not checks["native_development_controls_passed"]:
                raise RuntimeError(ui.get("error", "Native imaging controls failed"))
            for step in ("develop_visible_and_hit_testable", "actual_png_exr_receipt_downloads_and_media_admission",
                         "developed_image_used_by_actual_paused_frame_renderer", "normal_timeline_edit_saved"):
                checks[step] = step in ui.get("steps", [])
            saved = store.get(project["id"])
            directory = store.project_dir(project["id"])
            asset = next(a for a in saved["assets"] if a["id"] == ui["asset_id"])
            artifact_dir = directory / "imaging/outputs" / ui["output_id"]
            receipt = json.loads((artifact_dir / "receipt.json").read_text())
            checks["saved_timeline_uses_admitted_developed_asset"] = len(saved["clips"]) == 1 and saved["clips"][0]["asset_id"] == asset["id"]
            checks["source_recipe_and_runtime_are_in_receipt"] = receipt["operation"] == operation and {"numpy", "opencolorio", "OpenEXR"}.issubset(receipt["versions"])
            checks["display_asset_matches_preserved_output"] = asset["sha256"] == receipt["artifacts"]["display"]["sha256"] == hashlib.sha256((artifact_dir / "display.png").read_bytes()).hexdigest()
            checks["float_download_identity_matches_receipt"] = hashlib.sha256((artifact_dir / "linear.exr").read_bytes()).hexdigest() == receipt["artifacts"]["linear"]["sha256"] and (artifact_dir / "linear.exr").stat().st_size == ui["exr_download_bytes"]
            checks["receipt_is_owned_by_admitted_asset"] = asset["provenance"]["receipt_sha256"] == hashlib.sha256((artifact_dir / "receipt.json").read_bytes()).hexdigest()
            if operation == "raw":
                checks["camera_raw_was_imported_through_file_input"] = ui["source_id"] == result["camera_fixture"]["sha256"] and "real_raw_file_input_and_sensor_controls" in ui["steps"]
                checks["actual_raw_settings_executed"] = receipt["recipe"]["user_wb"] == [2.25, 1., .9, 1.] and receipt["recipe"]["half_size"] and receipt["recipe"]["highlight"] == "blend" and "libraw" in receipt["versions"]
            elif operation == "hdr_merge":
                checks["actual_radiance_above_one_preserved"] = receipt["linear_statistics"]["max"] > 8 and receipt["source_details"]["unrecovered_pixels"] == 0
                checks["all_explicit_bracket_times_executed"] = [entry["exposure_time"] for entry in receipt["recipe"]["brackets"]] == [.025, .1, .4]
            else:
                checks["actual_ocio_view_and_exposure_executed"] = receipt["recipe"]["view"] == "Un-tone-mapped" and receipt["recipe"]["exposure"] == 1.25
            png_pixel = read_generated_png16(artifact_dir / "display.png")
            pipeline = saved["clips"][0].get("color_pipeline", {})
            checks["saved_clip_has_explicit_srgb_display_input"] = (
                pipeline.get("version") == 1 and pipeline.get("enabled") is True
                and pipeline.get("input_transfer") == "srgb"
                and pipeline.get("input_primaries") == "rec709"
                and pipeline.get("lut") is None
            )
            if operation != "raw":
                checks["native_picture_matches_actual_developed_png"] = all(abs(a - round(b * 255)) <= 2 for a, b in zip(ui["developed_pixel"], png_pixel))
                # Independent IEC sRGB inverse + BT.709 OETF expectation. The
                # image has already passed its OCIO display view; the timeline
                # changes encoding only, with no second ACES/tone-map operation.
                # Uniform sources avoid resampling and camera-content ambiguity.
                expected = []
                for encoded in png_pixel[:3]:
                    linear = encoded / 12.92 if encoded <= .04045 else ((encoded + .055) / 1.055) ** 2.4
                    rec709 = 4.5 * linear if linear < .018 else 1.099 * linear ** .45 - .099
                    expected.append(round(max(0, min(1, rec709)) * 255))
                result["independent_rec709_expected_pixel"] = expected
                checks["native_timeline_matches_independent_srgb_to_rec709"] = all(
                    abs(actual - wanted) <= 4 for actual, wanted in zip(ui["timeline_frame"]["pixel"][:3], expected)
                ) and len(ui["timeline_frame"]["pixel"][:3]) == 3
            preview = directory / "previews" / Path(unquote(urlsplit(ui["timeline_frame"]["url"]).path)).name
            checks["actual_renderer_frame_exists"] = preview.is_file() and preview.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            # Render a short copy of the normal saved image edit, preserving the
            # real UI project. This verifies that normal movie export consumes
            # the developed image through the same established graph.
            export_project = copy.deepcopy(saved)
            export_project["clips"][0]["duration"] = 2
            movie = output / ("ENGINE_TEST_imaging_" + operation + "_export.mp4")
            event = threading.Event()
            timer = threading.Timer(budget(2.3, .4), event.set)
            timer.start()
            try:
                render_project(export_project, directory, movie, profile="h264", cancel_event=event)
            finally:
                timer.cancel()
            decoded = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-threads", "1", "-i", str(movie),
                                      "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-threads", "1", "pipe:1"],
                                     capture_output=True, check=True, timeout=budget(.8, .2)).stdout
            pixel = list(decoded[(45 * 160 + 80) * 3:(45 * 160 + 80) * 3 + 3])
            checks["movie_export_matches_actual_paused_frame"] = len(pixel) == 3 and all(abs(a - b) <= 9 for a, b in zip(pixel, ui["timeline_frame"]["pixel"][:3]))
            result["export_center_pixel"] = pixel
            for filename in ("display.png", "linear.exr", "receipt.json"):
                shutil.copy2(artifact_dir / filename, output / ("ENGINE_TEST_imaging_" + operation + "_" + filename))
            shutil.copy2(preview, output / ("ENGINE_TEST_imaging_" + operation + "_timeline.png"))
            checks["native_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000
            checks["exactly_one_real_imaging_job"] = sum(job.get("kind") == "imaging" for job in store.jobs.values()) == 1
            result["passed"] = all(checks.values())
            if not result["passed"]:
                result["error"] = "Failed checks: " + ", ".join(name for name, passed in checks.items() if not passed)
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            if store and project:
                (output / ("ENGINE_TEST_imaging_" + operation + "_project.json")).write_text(json.dumps(store.get(project["id"]), indent=2), encoding="utf-8")
            if server:
                server.shutdown()
                server.server_close()
            if thread:
                thread.join(timeout=.5)
            if store:
                store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["screenshot"] = str(screenshot) if screenshot.is_file() else None
    (output / ("ENGINE_TEST_imaging_" + operation + "_report.json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--operation", choices=["ocio", "hdr_merge", "raw"], default="ocio")
    parser.add_argument("--raw-file", type=Path, default=os.environ.get("CINEMATICUM_RAW_TEST_FILE"))
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Actual macOS WKWebView is required; no native imaging acceptance claimed."}))
        return 0
    if not args.binary or not args.binary.is_file():
        parser.error("Compile macos/SmokeTest.swift and pass its executable with --binary.")
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-imaging-webkit-TEST-evidence-"))
    result = run(args.binary, output, args.operation, args.raw_file)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
