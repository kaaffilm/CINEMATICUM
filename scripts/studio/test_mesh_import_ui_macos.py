#!/usr/bin/env python3
"""Real WKWebView OBJ file-input, own viewport, history and saved-data acceptance.

Uses an isolated temporary Studio workspace. Does not change the user's film.
Compile macos/SmokeTest.swift once and pass --binary. Real headless Blender
geometry/render acceptance is separately performed by test_spatial_blender.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from scene import pose_at, validate_scene
from server import Server, Store
from spatial_import import import_obj
from test_spatial_blender import OBJ, MTL


def run(binary, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    screenshot = output / "ENGINE_TEST_mesh_import_webkit.png"
    result = {"passed": False, "browser": "WKWebView", "fixture": "ENGINE TEST imported mesh — not a film", "checks": {}}
    checks, started = result["checks"], time.monotonic()
    deadline = started + 17.5

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The mesh import acceptance exceeded its 18-second budget.")
        return min(maximum, remaining)

    payload = {"name": "ENGINE_TEST.obj", "obj": OBJ,
               "materials": {"ENGINE_TEST.mtl": MTL + "map_Kd ENGINE_TEST_unselected_texture.png\n"}}
    with tempfile.TemporaryDirectory(prefix="cinematicum-mesh-webkit-TEST-") as temporary:
        work = Path(temporary)
        store = Store(work / "workspace")
        server = thread = project = None
        try:
            project = store.new_project({"name": "ENGINE TEST — Imported mesh browser fixture", "fps": 24, "width": 160, "height": 90})
            script = work / "MeshImportSmoke.js"
            script.write_text("const MESH_IMPORT_TEST=" + json.dumps(payload, ensure_ascii=True) + ";\n" +
                              (Path(__file__).parent / "macos" / "MeshImportSmoke.js").read_text(), encoding="utf-8")
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
            thread.start()
            # SmokeTest.swift reserves up to two further seconds for its
            # snapshot. Keep that failure-report path inside the outer budget.
            native_timeout = budget(13.3, 3)
            process = subprocess.run([str(Path(binary).resolve()), "--url", f"http://127.0.0.1:{server.server_port}",
                                      "--output", str(screenshot), "--script", str(script),
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
                raise RuntimeError("WebKit returned no result: " + (process.stderr or process.stdout)[-2500:])
            result["ui"], result["helper_exit_code"] = ui, process.returncode
            if process.stderr.strip():
                result["helper_stderr_tail"] = process.stderr[-1800:]
            checks["native_mesh_ui_passed"] = ui.get("passed") is True and process.returncode == 0
            checks["failed_import_did_not_checkpoint"] = "reject_invalid_topology_without_project_mutation" in ui.get("steps", [])
            checks["one_import_checkpoint_and_actual_redraw"] = "import_is_one_undoable_checkpoint_and_redraws_after_redo" in ui.get("steps", [])
            saved = store.get(project["id"])
            spec = validate_scene(saved.get("settings", {}).get("scene", {}))
            objects = spec["objects"]
            expected = import_obj(payload)["objects"]
            expected_meshes = {item["mesh"]["source"]["material"]: item["mesh"] for item in expected}
            checks["two_imported_objects_saved"] = len(objects) == 2 and all(item["type"] == "mesh" for item in objects)
            checks["canonical_topology_and_corner_data_saved"] = all(item["mesh"] == expected_meshes[item["mesh"]["source"]["material"]] for item in objects)
            source_hash = hashlib.sha256(OBJ.encode()).hexdigest()
            checks["original_obj_provenance_saved"] = all(item["mesh"]["source"]["sha256"] == source_hash for item in objects)
            edited = next((item for item in objects if item["id"] == ui.get("edited_object_id")), {})
            checks["material_is_editable_in_own_inspector"] = edited.get("name") == "ENGINE TEST edited imported mesh" and edited.get("material", {}).get("color") == "#3f87d5"
            keys = {key["frame"]: key for key in edited.get("keyframes", [])}
            checks["mesh_animation_and_easing_saved"] = (set(keys) == {1, 3} and keys[1].get("interpolation") == "ease_in"
                                                         and keys[1].get("position") == [.4, 0., 0.] and keys[3].get("position") == [1.4, 0., 0.]
                                                         and keys[3].get("rotation") == [0., 0., 40.])
            checks["saved_mesh_evaluates_like_viewport"] = bool(edited) and abs(pose_at(edited, 2)["position"][0] - .65) < 1e-9
            checks["no_unrequested_render_or_generated_media"] = not saved["assets"] and not saved["clips"] and not store.jobs
            picture = ui.get("webgl", {})
            checks["actual_shaded_webgl_picture"] = picture.get("colors", 0) >= 12 and picture.get("colorful_pixels", 0) >= 20
            checks["native_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            result["passed"] = all(checks.values())
            if not result["passed"]:
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(key for key, value in checks.items() if not value)
        except Exception as error:
            result["error"] = str(error)
        finally:
            if project:
                try:
                    (output / "ENGINE_TEST_mesh_saved_project.json").write_text(json.dumps(store.get(project["id"]), indent=2), encoding="utf-8")
                except Exception as error:
                    result["saved_evidence_error"] = str(error)
            if server:
                server.shutdown()
                server.server_close()
            if thread:
                thread.join(timeout=1)
            store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["screenshot"] = str(screenshot) if screenshot.is_file() else None
    (output / "ENGINE_TEST_mesh_import_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
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
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-mesh-webkit-TEST-evidence-"))
    result = run(args.binary, output)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
