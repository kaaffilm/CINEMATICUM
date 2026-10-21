#!/usr/bin/env python3
"""Actual native archive/download/upload/restore and decoded media acceptance.

The shipped controls save an actual clip and raster title, export their original
ProRes cut, download a real project ZIP, select those same bytes as a File,
restore a fresh project and export it. Python independently checks archive and
media identities, every decoded frame/sample, and the exact original metadata
bytes captured immediately before the real restore call. No job is simulated.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import zipfile

from color_pipeline import import_cube
from engine import probe_media
from project_archive import FORMAT, MANIFEST
from server import Server, Store
from test_editing_ui_macos import read_helper_result


HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT, FPS, FRAMES = 160, 90, 24, 8
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(binary, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + 15.5
    result = {"passed": False, "browser": "WKWebView", "fixture": "SYNTHETIC ENGINE TEST — NOT A FILM", "checks": {}}
    checks, screenshot = result["checks"], output / "ENGINE_TEST_archive_webkit.png"

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("Archive acceptance exceeded its 15.5-second execution budget.")
        return min(maximum, remaining)

    def command(arguments, maximum=2.5):
        return subprocess.run(arguments, check=True, capture_output=True, timeout=budget(maximum)).stdout

    with tempfile.TemporaryDirectory(prefix="cinematicum-archive-webkit-ENGINE-TEST-") as temporary:
        work, store, server, thread = Path(temporary), None, None, None
        try:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg or not shutil.which("ffprobe"):
                raise RuntimeError("Actual FFmpeg/ffprobe are required for source and output media.")
            fixture = work / "ENGINE_TEST_archive_source.mp4"
            command([ffmpeg, "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1", "-threads", "1",
                     "-f", "lavfi", "-i", f"testsrc2=s={WIDTH}x{HEIGHT}:r={FPS}:d=0.5",
                     "-f", "lavfi", "-i", "sine=f=660:r=48000:d=0.5", "-frames:v", "12", "-t", "0.5",
                     "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-threads", "1", "-c:a", "aac", str(fixture)])
            fixture_hash = sha256(fixture)
            store = Store(work / "workspace")
            project = store.new_project({"name": "ENGINE TEST archive — actual edit", "width": WIDTH, "height": HEIGHT, "fps": FPS})
            asset = store.admit(project["id"], fixture, fixture.name, {"fixture": "ENGINE TEST"})
            original = store.project_dir(project["id"])
            lut = import_cube('TITLE "ENGINE TEST archive palette"\nLUT_1D_SIZE 2\n0 0 0\n1 1 1\n', original)
            workflow = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "CINEMATICUM_POSITIVE_PROMPT"}}}
            (original / "workflow.json").write_text(json.dumps(workflow) + "\n", encoding="utf-8")
            observed = {}
            real_restore = store.archive_restore

            def observe_restore(project_id, incoming):
                # Read-only observation; the real production method, upload,
                # asynchronous job, validation and publication all still run.
                directory = store.project_dir(project_id)
                observed.update(project_id=project_id, project_bytes=(directory / "project.json").read_bytes(),
                                assets_bytes=(directory / "assets.json").read_bytes(), upload_sha256=sha256(incoming),
                                upload_bytes=Path(incoming).stat().st_size)
                return real_restore(project_id, incoming)

            store.archive_restore = observe_restore
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            thread.start()
            native_timeout = budget(12.3, 2)
            process = subprocess.run([str(Path(binary).resolve()), "--url", f"http://127.0.0.1:{server.server_port}/",
                                      "--output", str(screenshot), "--script", str(HERE / "macos/ArchiveSmoke.js"),
                                      "--timeout", str(round(native_timeout, 2))], capture_output=True, text=True,
                                     timeout=budget(native_timeout + .5, .7))
            ui = read_helper_result(process)
            result.update(ui=ui, helper_exit_code=process.returncode)
            if process.stderr:
                result["helper_stderr_tail"] = process.stderr[-1200:]
            checks["actual_native_archive_controls"] = process.returncode == 0 and ui.get("passed") is True
            checks["no_browser_errors"] = not ui.get("page_errors", [])
            for step in ("author_and_save_actual_media_and_raster_title", "render_original_prores_cut",
                         "download_real_verified_project_archive", "upload_real_file_restore_new_identity_keep_original",
                         "explicitly_open_restored_edit_with_all_media_relationships", "render_restored_prores_cut"):
                checks[step] = step in ui.get("steps", [])
            source = store.get(project["id"])
            restored_id = ui.get("restored_project_id")
            checks["new_distinct_project_identity"] = isinstance(restored_id, str) and restored_id != project["id"] and len(store.projects()) == 2
            checks["original_project_and_inventory_bytes_unchanged"] = bool(observed) and observed["project_id"] == project["id"] and observed["project_bytes"] == (original / "project.json").read_bytes() and observed["assets_bytes"] == (original / "assets.json").read_bytes()
            with store.lock:
                jobs = copy.deepcopy(list(store.jobs.values()))
            exports = [j for j in jobs if j["kind"] == "archive-export" and j["state"] == "completed"]
            restores = [j for j in jobs if j["kind"] == "archive-restore" and j["state"] == "completed"]
            checks["one_real_archive_export_and_restore"] = len(exports) == len(restores) == 1
            checks["no_generation_or_blender_execution"] = all(j["kind"] in {"render", "frame-preview", "archive-export", "archive-restore"} for j in jobs)
            if exports:
                receipt = exports[0]["result"]
                archive = original / "exports" / receipt["filename"]
                identity = sha256(archive)
                checks["download_and_raw_upload_are_identical_archive_bytes"] = identity == receipt["sha256"] == observed.get("upload_sha256") and archive.stat().st_size == observed.get("upload_bytes") == ui.get("archive_bytes")
                checks["download_url_is_actual_archive"] = Path(urlsplit(ui.get("archive_href", "")).path).name == archive.name
                with zipfile.ZipFile(archive) as package:
                    manifest = json.loads(package.read(MANIFEST))
                    names = set(package.namelist())
                    checks["manifest_has_source_media_title_lut_and_workflow"] = manifest["format"] == FORMAT and manifest["project_id"] == project["id"] and asset["path"] in names and "workflow.json" in names and "color/luts/" + lut["sha256"] + ".cube" in names and bool(source["titles"]) and next(a["path"] for a in source["assets"] if a["id"] == source["titles"][0]["asset_id"]) in names
                    checks["unrelated_movie_and_transient_state_excluded"] = not any(name.startswith(("previews/", "waveforms/", "recovery/")) or name.startswith("exports/") and name.endswith(".mov") for name in names)
                shutil.copy2(archive, output / "ENGINE_TEST_edit.cinematicum.zip")
                result["archive"] = {"sha256": identity, "bytes": archive.stat().st_size, "files": receipt["files"]}
            if restored_id:
                restored = store.get(restored_id)
                fresh = store.project_dir(restored_id)
                checks["restored_authoring_and_inventory_equal"] = all(source[key] == restored[key] for key in ("clips", "titles", "assets", "settings", "tracks", "frame_rate"))
                checks["real_raster_title_reference_preserved"] = len(restored["titles"]) == 1 and restored["titles"][0].get("asset_id") == ui.get("title_asset_id") and restored["titles"][0]["text"] == "ENGINE TEST archive"
                checks["original_and_restored_media_hashes_identical"] = all(sha256(original / item["path"]) == sha256(fresh / item["path"]) == item["sha256"] for item in source["assets"]) and sha256(original / asset["path"]) == fixture_hash
                checks["workflow_and_unused_palette_preserved"] = (original / "workflow.json").read_bytes() == (fresh / "workflow.json").read_bytes() and (original / "color/luts" / (lut["sha256"] + ".cube")).read_bytes() == (fresh / "color/luts" / (lut["sha256"] + ".cube")).read_bytes()
                checks["restore_receipt_matches_download_and_source"] = restored["archive_restore"]["source_project_id"] == project["id"] and restored["archive_restore"]["archive_sha256"] == observed["upload_sha256"] and restored["archive_restore"]["issuance_effect"] == "NONE"
                outputs = []
                for label, p, directory, href in (("original", source, original, ui.get("source_render_href", "")),
                                                  ("restored", restored, fresh, ui.get("restored_render_href", ""))):
                    rendered = [j for j in jobs if j["project_id"] == p["id"] and j["kind"] == "render" and j["state"] == "completed"]
                    checks[label + "_one_real_prores_export"] = len(rendered) == 1 and rendered[0]["result"].get("profile") == "prores"
                    if len(rendered) != 1:
                        continue
                    receipt = rendered[0]["result"]
                    movie = directory / "exports" / receipt["filename"]
                    metadata = probe_media(movie)
                    checks[label + "_render_identity_and_clock"] = sha256(movie) == receipt["sha256"] and metadata["frames"] == FRAMES and (metadata["width"], metadata["height"]) == (WIDTH, HEIGHT) and Path(urlsplit(href).path).name == movie.name
                    rgb = command([ffmpeg, "-v", "error", "-nostdin", "-i", str(movie), "-map", "0:v:0", "-an", "-pix_fmt", "rgb24", "-threads", "1", "-f", "rawvideo", "pipe:1"])
                    pcm = command([ffmpeg, "-v", "error", "-nostdin", "-i", str(movie), "-map", "0:a:0", "-vn", "-f", "s16le", "pipe:1"])
                    outputs.append((rgb, pcm))
                    shutil.copy2(movie, output / ("ENGINE_TEST_" + label + "_archive_cut.mov"))
                checks["every_decoded_frame_and_pcm_sample_identical"] = len(outputs) == 2 and len(outputs[0][0]) == FRAMES * WIDTH * HEIGHT * 3 and bool(outputs[0][1]) and outputs[0] == outputs[1]
                if len(outputs) == 2:
                    result["decoded"] = {"frames": len(outputs[0][0]) // (WIDTH * HEIGHT * 3), "rgb_sha256": hashlib.sha256(outputs[0][0]).hexdigest(),
                                         "pcm_bytes": len(outputs[0][1]), "pcm_sha256": hashlib.sha256(outputs[0][1]).hexdigest()}
                (output / "ENGINE_TEST_restored_project.json").write_text(json.dumps(restored, indent=2) + "\n", encoding="utf-8")
            checks["native_archive_screenshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes().startswith(PNG_SIGNATURE)
            result["jobs"] = [{"kind": job["kind"], "state": job["state"], **({"error": job["error"]} if job.get("error") else {})} for job in jobs]
            if not all(checks.values()):
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(name for name, passed in checks.items() if not passed)
        except Exception as error:
            result["error"] = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                result["process_error"] = (error.stderr or b"").decode(errors="replace")[-1600:]
        finally:
            if server:
                server.shutdown()
                server.server_close()
            if thread:
                thread.join(timeout=.2)
            if store:
                store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    checks["bounded_whole_run"] = result["elapsed_seconds"] < 16
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    (output / "ENGINE_TEST_archive_report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Actual WKWebView acceptance requires macOS; no native result is simulated."}))
        return 0
    if not args.binary or not args.binary.is_file():
        parser.error("Supply the compiled macos/SmokeTest.swift executable with --binary.")
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-archive-ENGINE-TEST-evidence-"))
    result = run(args.binary, output)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
