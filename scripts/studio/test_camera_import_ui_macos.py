#!/usr/bin/env python3
"""Actual WKWebView camera file input, candidate selection and shared history.

Uses an isolated temporary project and the precompiled macos/SmokeTest.swift
helper. It does not alter the user's film. Blender reprojection is a separate
native proof in verify_camera_native.py.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from camera_io import import_camera
from scene import default_scene, validate_scene
from server import Server, Store
from test_camera_io import colmap_payload, fspy_bytes


def run(binary, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    screenshot = output / "ENGINE_TEST_camera_import_webkit.png"
    result = {"passed": False, "browser": "WKWebView", "fixture": "ENGINE TEST calibrated cameras — not a film", "checks": {}}
    checks, started = result["checks"], time.monotonic()
    deadline = started + 17.5

    def budget(maximum, reserve=0):
        remaining = deadline-time.monotonic()-reserve
        if remaining <= .1:
            raise TimeoutError("Camera import acceptance exceeded its 18-second budget.")
        return min(maximum, remaining)

    data = fspy_bytes()
    fspy = {"format": "fspy", "name": "ENGINE_TEST_camera.fspy", "data_base64": base64.b64encode(data).decode()}
    colmap = colmap_payload()
    colmap["images_text"] += "93 1 0 0 0 0 -2 0 42 second camera.png\n\n"
    expected_fspy = import_camera(fspy, 192, 128)["cameras"][0]["camera"]
    expected_colmap = import_camera(colmap, 192, 128)["cameras"][1]["camera"]
    with tempfile.TemporaryDirectory(prefix="cinematicum-camera-webkit-TEST-") as temporary:
        work = Path(temporary)
        store = Store(work/"workspace")
        server = thread = project = None
        try:
            project = store.new_project({"name": "ENGINE TEST — Calibrated camera matching", "width": 192, "height": 128, "fps": 24})
            spec = default_scene(192, 128)
            spec["frame_end"] = 3
            spec["objects"] = [{"id": "reference_cube", "name": "ENGINE TEST retained geometry", "type": "cube",
                                "position": [0, 0, 1], "rotation": [12, 25, 7], "scale": [.6, .6, .6],
                                "material": {"color": "#d8a35a", "roughness": .3, "metallic": .1}}]
            spec["camera"].update(roll=12, keyframes=[{"frame": 1, "roll": 12}, {"frame": 3, "roll": 25}])
            spec = validate_scene(spec)
            project["settings"]["scene"] = spec
            project["settings"]["engine_test_sentinel"] = "retained"
            project = store.save(project["id"], project)
            script = work/"CameraImportSmoke.js"
            fixture = {"fspy_base64": fspy["data_base64"], "fspy_camera": expected_fspy, "colmap": colmap, "colmap_camera": expected_colmap}
            script.write_text("const CAMERA_IMPORT_TEST="+json.dumps(fixture, ensure_ascii=True)+";\n"+
                              (Path(__file__).parent/"macos"/"CameraImportSmoke.js").read_text(), encoding="utf-8")
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            thread.start()
            native_timeout = budget(13.3, 3)
            process = subprocess.run([str(Path(binary).resolve()), "--url", "http://127.0.0.1:%s"%server.server_port,
                                      "--output", str(screenshot), "--script", str(script), "--timeout", str(round(native_timeout, 2))],
                                     capture_output=True, text=True, timeout=budget(native_timeout+2.2, .8))
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
                raise RuntimeError("WebKit returned no camera result: "+(process.stderr or process.stdout)[-2500:])
            result["ui"], result["helper_exit_code"] = ui, process.returncode
            if process.stderr.strip():
                result["helper_stderr_tail"] = process.stderr[-1800:]
            checks["native_camera_ui_passed"] = ui.get("passed") is True and process.returncode == 0
            for step in ("reject_original_duplicate_json_without_history", "native_binary_fspy_input_apply_undo_redo",
                         "native_colmap_pair_pose_selection_and_single_undo", "save_calibration_with_unrelated_scene_preserved"):
                checks[step] = step in ui.get("steps", [])
            saved = store.get(project["id"])
            final = validate_scene(saved.get("settings", {}).get("scene", {}))
            camera = final["camera"]
            checks["selected_pose_calibration_saved"] = all(camera[key] == value for key, value in expected_colmap.items())
            checks["prior_camera_keys_removed"] = camera["keyframes"] == []
            checks["geometry_lights_world_render_preserved"] = all(final[key] == spec[key] for key in spec if key != "camera")
            checks["unrelated_project_setting_preserved"] = saved["settings"].get("engine_test_sentinel") == "retained"
            source = saved["settings"].get("camera_import", {}).get("source", {})
            checks["selected_pose_source_record_saved"] = source.get("image_id") == 93 and source.get("camera_id") == 42 and source.get("format") == "colmap"
            checks["review_did_not_generate_or_import_media"] = not saved["assets"] and not saved["clips"] and not store.jobs
            checks["native_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            result["passed"] = all(checks.values())
            if not result["passed"]:
                result["error"] = ui.get("error") or "Failed checks: "+", ".join(key for key, value in checks.items() if not value)
        except Exception as error:
            result["error"] = str(error)
        finally:
            if project:
                try:
                    (output/"ENGINE_TEST_camera_saved_project.json").write_text(json.dumps(store.get(project["id"]), indent=2), encoding="utf-8")
                except Exception as error:
                    result["saved_evidence_error"] = str(error)
            if server:
                server.shutdown()
                server.server_close()
            if thread:
                thread.join(timeout=1)
            store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic()-started, 3)
    result["screenshot"] = str(screenshot) if screenshot.is_file() else None
    (output/"ENGINE_TEST_camera_import_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
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
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-camera-webkit-TEST-evidence-"))
    result = run(args.binary, output)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
