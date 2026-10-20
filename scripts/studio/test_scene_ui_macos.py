#!/usr/bin/env python3
"""Exercise real WKWebView scene authoring and Blender rendering on macOS.

Compile macos/SmokeTest.swift separately, then pass its executable with --binary.
The native helper operates DOM controls using macos/SceneSmoke.js. This harness
independently checks the saved recipe, actual decoded movie, retained Blender
source, and download endpoint. All geometry and evidence are explicitly TEST.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from engine import probe_media
from scene import validate_scene
from server import Server, Store


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def run(binary, evidence):
    evidence = Path(evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    result = {"passed": False, "browser": "WKWebView", "fixture": "SYNTHETIC ENGINE TEST SCENE — NOT A FILM", "checks": {}}
    checks = result["checks"]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="cinematicum-scene-webkit-TEST-") as temporary:
        scratch = Path(temporary)
        store = Store(scratch / "workspace")
        server = thread = project = None
        screenshot = evidence / "ENGINE_TEST_scene_webkit.png"
        try:
            project = store.new_project({"name": "ENGINE TEST — Authored 3D browser fixture", "fps": 12, "width": 160, "height": 90})
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            command = [str(Path(binary).resolve()), "--url", origin, "--output", str(screenshot),
                       "--script", str(Path(__file__).parent / "macos" / "SceneSmoke.js"), "--timeout", "16"]
            process = subprocess.run(command, capture_output=True, text=True, timeout=18)
            ui = None
            for line in reversed(process.stdout.splitlines()):
                try:
                    candidate = json.loads(line)
                    if isinstance(candidate, dict) and "passed" in candidate:
                        ui = candidate
                        break
                except ValueError:
                    continue
            if ui is None:
                raise RuntimeError("WebKit helper returned no JSON result: " + (process.stderr or process.stdout)[-3000:])
            result["ui"] = ui
            result["helper_exit_code"] = process.returncode
            if process.stderr.strip():
                result["helper_stderr_tail"] = process.stderr[-1800:]
            checks["native_scene_ui_passed"] = ui.get("passed") is True and process.returncode == 0
            checks["undo_redo_retains_completed_media"] = ("undo_redo_preserves_rendered_media" in ui.get("steps", [])
                                                           and 1 <= ui.get("undo_count", 0) <= 3
                                                           and ui.get("undone_rotation") == 0)
            picture = ui.get("webgl", {})
            checks["actual_webgl_picture"] = (picture.get("width", 0) > 32 and picture.get("height", 0) > 32
                                               and picture.get("unique_colors", 0) >= 4
                                               and picture.get("nonuniform_pixels", 0) >= 20
                                               and picture.get("changed_pixels_from_empty", 0) >= 8)
            saved = store.get(project["id"])
            recipe = saved.get("settings", {}).get("scene", {})
            objects = recipe.get("objects", [])
            cube = objects[0] if len(objects) == 1 else {}
            keys = {key["frame"]: key for key in cube.get("keyframes", [])}
            checks["one_authored_cube_saved"] = len(objects) == 1 and cube.get("type") == "cube" and cube.get("name") == "ENGINE TEST — authored cube"
            checks["scene_format_saved"] = (recipe.get("width"), recipe.get("height"), recipe.get("frame_end"), recipe.get("samples")) == (160, 90, 2, 4)
            checks["material_saved"] = cube.get("material", {}).get("color") == "#4d9bd8"
            checks["two_pose_keys_saved"] = len(keys) == 2 and set(keys) == {1, 2}
            checks["first_pose_saved"] = keys.get(1, {}).get("position") == [0, 0, 1] and keys.get(1, {}).get("rotation") == [0, 0, 0]
            checks["second_pose_saved"] = keys.get(2, {}).get("position") == [.6, 0, 1] and keys.get(2, {}).get("rotation") == [0, 0, 25]
            with store.lock:
                jobs = json.loads(json.dumps([job for job in store.jobs.values() if job["project_id"] == project["id"] and job["kind"] == "scene"]))
            result["jobs"] = jobs
            completed = [job for job in jobs if job["state"] == "completed"]
            checks["actual_scene_job_completed"] = len(completed) == 1
            if completed:
                job = completed[0]
                output = job["result"]
                asset = output["asset"]
                movie = store.project_dir(project["id"]) / asset["path"]
                source = store.project_dir(project["id"]) / "exports" / output["scene_filename"]
                metadata = probe_media(movie)
                result["media"] = metadata
                checks["exact_two_frames"] = metadata["frames"] == 2 and metadata["width"] == 160 and metadata["height"] == 90
                checks["expected_duration"] = abs(metadata["duration"] - 2 / 12) < .03
                decoded = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(movie),
                                          "-map", "0:v:0", "-frames:v", "2", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
                                         check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4).stdout
                frame_bytes = 160 * 90 * 3
                checks["movie_decodes_two_frames"] = len(decoded) == frame_bytes * 2
                if len(decoded) == frame_bytes * 2:
                    first, second = decoded[:frame_bytes], decoded[frame_bytes:]
                    changed = sum(abs(a - b) > 10 for a, b in zip(first, second))
                    result["changed_rendered_channels"] = changed
                    checks["rendered_animation_changes_pixels"] = changed > 60
                    colors = {first[index:index + 3] for index in range(0, frame_bytes, 3)}
                    checks["rendered_picture_is_nonuniform"] = len(colors) > 32
                provenance = asset.get("provenance", {})
                checks["actual_blender_provenance"] = provenance.get("backend") == "blender-authored-scene" and provenance.get("renderer") == "Cycles CPU"
                checks["movie_hash_matches"] = digest(movie) == asset.get("sha256") == provenance.get("output_sha256")
                checks["blender_source_retained"] = source.is_file() and source.stat().st_size > 1000
                checks["blender_source_hash_matches"] = checks["blender_source_retained"] and digest(source) == output.get("scene_sha256") == provenance.get("scene_sha256")
                normalized = validate_scene(recipe, width=160, height=90)
                recipe_hash = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                checks["rendered_recipe_matches_saved_scene"] = recipe_hash == provenance.get("recipe_sha256")
                checks["browser_received_source_download"] = ui.get("scene_href") == output["scene_url"] + "?download=1"
                with urllib.request.urlopen(origin + output["scene_url"] + "?download=1", timeout=2) as response:
                    downloaded = response.read(16 * 1024 * 1024 + 1)
                    checks["source_download_route"] = (response.status == 200 and "attachment" in response.headers.get("Content-Disposition", "")
                                                         and hashlib.sha256(downloaded).hexdigest() == output.get("scene_sha256"))
                clips = saved["clips"]
                checks["authored_movie_on_timeline"] = len(clips) == 1 and clips[0]["asset_id"] == asset["id"] and clips[0]["duration"] == 2 and ui.get("asset_id") == asset["id"]
                for source_path, filename in ((movie, "ENGINE_TEST_authored_scene.mp4"), (source, "ENGINE_TEST_authored_scene.blend")):
                    shutil.copy2(source_path, evidence / filename)
                result["movie"] = str(evidence / "ENGINE_TEST_authored_scene.mp4")
                result["blender_source"] = str(evidence / "ENGINE_TEST_authored_scene.blend")
            checks["webkit_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            result["passed"] = bool(checks) and all(checks.values())
            if not result["passed"]:
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(key for key, value in checks.items() if not value)
        except Exception as error:
            result["error"] = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                detail = error.stderr or b""
                result["process_error"] = (detail.decode(errors="replace") if isinstance(detail, bytes) else detail)[-3000:]
        finally:
            if project is not None:
                try:
                    (evidence / "ENGINE_TEST_scene_saved_project.json").write_text(json.dumps(store.get(project["id"]), indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception as error:
                    result["saved_project_evidence_error"] = str(error)
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=1)
            store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["screenshot"] = str(screenshot) if screenshot.is_file() else None
    result["evidence_directory"] = str(evidence)
    (evidence / "ENGINE_TEST_scene_report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify native 3D scene authoring through actual WebKit and Blender")
    parser.add_argument("--binary", type=Path, help="Previously compiled macos/SmokeTest.swift executable")
    parser.add_argument("--output", type=Path, help="Folder for screenshot, authored test movie/source, and JSON evidence")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Native scene acceptance requires macOS WKWebView and installed Blender."}))
        return 0
    if not args.binary or not args.binary.is_file():
        parser.error("Compile macos/SmokeTest.swift separately and pass its executable with --binary.")
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-scene-webkit-TEST-evidence-"))
    result = run(args.binary, output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
