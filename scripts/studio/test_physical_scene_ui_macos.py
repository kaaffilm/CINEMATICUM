#!/usr/bin/env python3
"""Native WKWebView physical controls, undo, animation and project persistence.

This exercises DOM controls only. test_physical_scene_blender.py separately
reopens and renders the actual retained Blender source for numerical proof.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from scene import validate_scene
from server import Server, Store


def run(binary, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {"passed": False, "fixture": "SYNTHETIC ENGINE TEST — NOT A FILM", "browser": "WKWebView", "checks": {}}
    checks = result["checks"]
    began = time.monotonic()
    screenshot = output / "ENGINE_TEST_physical_controls.png"
    with tempfile.TemporaryDirectory(prefix="cinematicum-physical-webkit-TEST-") as temporary:
        store = Store(Path(temporary) / "workspace")
        server = thread = project = None
        try:
            project = store.new_project({"name": "ENGINE TEST physical authoring", "fps": 12, "width": 160, "height": 90})
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
            thread.start()
            process = subprocess.run([str(Path(binary).resolve()), "--url", "http://127.0.0.1:" + str(server.server_port),
                                      "--output", str(screenshot), "--script", str(Path(__file__).parent / "macos" / "PhysicalSceneSmoke.js"),
                                      "--timeout", "12"], capture_output=True, text=True, timeout=15)
            ui = None
            for line in reversed(process.stdout.splitlines()):
                try:
                    value = json.loads(line)
                    if isinstance(value, dict) and "passed" in value:
                        ui = value
                        break
                except ValueError:
                    pass
            if ui is None:
                raise RuntimeError("Native helper returned no physical-control result: " + (process.stderr or process.stdout)[-1800:])
            result["ui"] = ui
            checks["actual_native_controls_and_undo"] = process.returncode == 0 and ui.get("passed") is True
            saved = store.get(project["id"])
            spec = saved["settings"]["scene"]
            (output / "ENGINE_TEST_physical_saved_project.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
            checks["normalized_physical_scene_saved"] = validate_scene(spec, width=160, height=90) == spec
            camera = spec["camera"]
            checks["one_physical_sphere"] = len(spec["objects"]) == 1 and spec["objects"][0]["name"] == "ENGINE TEST physical sphere"
            mat = spec["objects"][0]["material"]
            checks["principled_values_saved"] = mat["transmission"] == 1 and mat["ior"] == 1.47 and mat["emission_color"] == "#ff9d45" and mat["emission_strength"] == .25
            checks["physical_lens_saved"] = camera["sensor_height_mm"] == 36 and abs(camera["fov"] - math.degrees(2 * math.atan(36 / 100))) < 1e-8
            checks["aperture_shape_saved"] = camera["dof_enabled"] and camera["aperture_blades"] == 7 and camera["aperture_rotation"] == 15 and camera["aperture_ratio"] == 1.3
            keys = {item["frame"]: item for item in camera["keyframes"]}
            checks["focus_pull_and_roll_keys_saved"] = set(keys) == {1, 2} and keys[1]["focus_distance"] == 3 and keys[2]["focus_distance"] == 6 and keys[1]["roll"] == 17 and keys[2]["roll"] == 25 and keys[1]["f_stop"] == 2.8 and keys[2]["f_stop"] == 5.6
            checks["calibrated_framing_saved"] = camera["focal_ratio"] == 1.2 and all(k["shift_x"] == .07 and k["shift_y"] == -.04 and "focal_ratio" not in k for k in keys.values())
            checks["light_paths_saved"] = spec["render"] == {"max_bounces": 7, "diffuse_bounces": 3, "glossy_bounces": 5,
                                                               "transmission_bounces": 6, "transparent_max_bounces": 4,
                                                               "seed": 37, "use_denoising": False}
            checks["native_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000
            result["passed"] = bool(checks) and all(checks.values())
            if not result["passed"]:
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(key for key, value in checks.items() if not value)
        except Exception as error:
            result["error"] = str(error)
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=1)
            store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    result["screenshot"] = str(screenshot) if screenshot.exists() else None
    (output / "ENGINE_TEST_physical_ui_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Native authoring acceptance requires macOS WKWebView."}))
        raise SystemExit(0)
    if not args.binary or not args.binary.is_file():
        parser.error("Compile macos/SmokeTest.swift and pass its executable with --binary.")
    result = run(args.binary, args.output)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
