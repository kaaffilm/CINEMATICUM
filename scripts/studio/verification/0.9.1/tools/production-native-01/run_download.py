#!/usr/bin/env python3
"""Actual production-class NSSavePanel/WKDownload acceptance in an isolated store.

Run after build.py on macOS. This neither installs an app nor changes a user's
project directory. The production delegate class is compiled unchanged; only
the test startup binds a separate actual Store/Server and observes native UI.
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
import threading
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(source, binary, output):
    source, binary, output = source.absolute(), binary.absolute(), output.absolute()
    if sys.platform != "darwin":
        raise ValueError("Actual AppKit/NSSavePanel acceptance requires macOS; no native result is simulated")
    build = json.loads((binary.parent / "build.json").read_text())
    production = source / "scripts/studio/macos/StudioApp.swift"
    if build.get("compiled") is not True or build.get("binary_sha256") != sha(binary):
        raise ValueError("Native helper does not match its actual compiled build receipt")
    if build.get("production_source_sha256") != sha(production):
        raise ValueError("Native helper did not compile the selected production class")
    output.mkdir(parents=True, exist_ok=False)
    work = output / "fixture"
    work.mkdir()
    downloads = output / "native-downloads"
    downloads.mkdir()
    report = {"schema": "cinematicum-production-native-download-v1", "passed": False,
              "scope": "Unchanged production StudioAppDelegate class with isolated startup; real NSSavePanel Save/Cancel and WKDownload; not an installed-bundle UI claim",
              "fixture": "SYNTHETIC ENGINE TEST ONLY — NOT FILM FOOTAGE",
              "build": build, "checks": {}, "installed_app_ui_certified": False,
              "existing_destination_replacement_certified": False,
              "accessibility_or_screen_recording_permission_requested": False}
    checks = report["checks"]
    started = time.monotonic()
    store = server = thread = None
    sys.path.insert(0, str(source / "scripts/studio"))
    from server import Server, Store
    from test_high_precision import WIDTH, HEIGHT, FPS, FRAMES, decode_rgba16, numeric_ramp, write_fixture
    from test_editing_ui_macos import read_helper_result
    try:
        fixture = write_fixture(work / "ENGINE_TEST_16bit_source.mkv", numeric_ramp())
        fixture_sha = sha(fixture)
        store = Store(work / "workspace")
        sentinel = store.new_project({"name": "ENGINE TEST reopen sentinel", "fps": FPS, "width": WIDTH, "height": HEIGHT})
        project = store.new_project({"name": "ENGINE TEST — native 16-bit SDR", "fps": FPS, "width": WIDTH, "height": HEIGHT})
        asset = store.admit(project["id"], fixture, fixture.name)
        identities = {"project_id": project["id"], "sentinel_id": sentinel["id"], "asset_id": asset["id"]}
        report["fixture_identity"] = identities
        report["source_fixture_sha256"] = fixture_sha
        script_source = source / "scripts/studio/macos/HighPrecisionSmoke.js"
        script = work / "high16-production-workflow.js"
        script.write_text("const HIGH16_TEST=" + json.dumps(identities) + ";\n" + script_source.read_text(), encoding="utf-8")
        report["ui_script_source_sha256"] = sha(script_source)
        report["bound_ui_script_sha256"] = sha(script)
        server = Server(0, store)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        origin = "http://127.0.0.1:" + str(server.server_port)
        command = [str(binary), "--mode", "download", "--url", origin + "/", "--evidence", str(downloads),
                   "--script", str(script), "--timeout", "40"]
        (work / "native-command.json").write_text(json.dumps(command, indent=2) + "\n")
        process = subprocess.run(command, capture_output=True, text=True, timeout=45)
        (output / "native.stdout").write_text(process.stdout)
        (output / "native.stderr").write_text(process.stderr)
        native = read_helper_result(process)
        report.update(native=native, native_returncode=process.returncode)
        checks["actual_native_class_gate"] = process.returncode == 0 and native.get("passed") is True
        checks["production_source_hash_unchanged_after_execution"] = sha(production) == build["production_source_sha256"]
        ui = native.get("ui", {})
        checks["real_ui_selected_exact_fixture"] = ui.get("passed") is True and ui.get("project_id") == project["id"]
        saved = store.get(project["id"])
        directory = store.project_dir(project["id"])
        report["saved_project"] = saved
        checks["saved_high16_transparent_project"] = saved.get("settings", {}).get("image_precision") == "high16" and saved["settings"].get("transparent_background") is True
        checks["reopen_sentinel_not_edited"] = store.get(sentinel["id"]).get("clips") == []
        with store.lock:
            jobs = copy.deepcopy([job for job in store.jobs.values() if job["project_id"] == project["id"]])
        completed = [job for job in jobs if job["kind"] == "render" and job["state"] == "completed"]
        checks["one_actual_completed_master_job"] = len(completed) == 1
        report["completed_render_jobs"] = completed
        if len(completed) == 1:
            receipt = completed[0]["result"]
            master = directory / "exports" / receipt["filename"]
            payload = master.read_bytes()
            expected_sha = hashlib.sha256(payload).hexdigest()
            target = downloads / "ENGINE_TEST_PRODUCTION_SAVED_MASTER.mkv"
            checks["download_link_binds_actual_completed_master"] = ui.get("download_href") == receipt["url"] + "?download=1" and ui.get("download_filename") == receipt["filename"]
            checks["server_master_matches_its_receipt"] = receipt.get("profile") == "master16" and expected_sha == receipt.get("sha256")
            checks["native_save_exact_bytes"] = target.is_file() and not target.is_symlink() and target.read_bytes() == payload
            checks["native_observation_matches_independent_hash"] = native.get("saved_file") == {"path": str(target), "bytes": len(payload), "sha256": expected_sha}
            checks["cancel_has_no_destination"] = not (downloads / "ENGINE_TEST_PRODUCTION_CANCELLED_MASTER.mkv").exists()
            checks["no_owned_partial_downloads_remain"] = not list(downloads.glob(".cinematicum-download-*.partial"))
            checks["cancel_kept_completed_master_intact"] = sha(master) == expected_sha
            probe = json.loads(subprocess.run([shutil.which("ffprobe"), "-v", "error", "-count_frames", "-show_streams",
                                              "-of", "json", str(target)], capture_output=True, text=True, check=True, timeout=10).stdout)
            streams = probe["streams"]
            video = next(item for item in streams if item["codec_type"] == "video")
            audio = next(item for item in streams if item["codec_type"] == "audio")
            report["downloaded_streams"] = streams
            checks["downloaded_ffv1_16bit_alpha_pcm"] = video["codec_name"] == "ffv1" and video["pix_fmt"] == "gbrap16le" and video["width"] == WIDTH and video["height"] == HEIGHT and int(video["nb_read_frames"]) == FRAMES and audio["codec_name"] == "pcm_s16le" and audio["channels"] == 2 and int(audio["sample_rate"]) == 48000
            pixels = decode_rgba16(target)
            checks["all_downloaded_frames_independently_decode"] = len(pixels) == WIDTH * HEIGHT * FRAMES
            checks["download_retains_fractional_alpha_and_more_than_256_colors"] = len({p[0] for p in pixels if p[3] > 32768}) > 256 and any(0 < p[3] < 65535 and p[3] % 257 for p in pixels)
        panels = native.get("panels", [])
        # The native observer obtains each window through an NSSavePanel cast;
        # AppKit may provide a private subclass with a different runtime name.
        checks["native_save_and_cancel_panels_observed"] = len(panels) == 2 and [item.get("operation") for item in panels] == ["save", "cancel"] and all(item.get("class") and item.get("title") == "Save CINEMATICUM export" for item in panels)
        pictures = []
        for panel in panels:
            picture = panel.get("picture", {})
            path = Path(picture.get("path", ""))
            pictures.append(path.parent == downloads and path.is_file() and not path.is_symlink()
                            and path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") and sha(path) == picture.get("sha256"))
        checks["actual_native_panel_captures_retained"] = len(pictures) == 2 and all(pictures)
        checks["admitted_source_preserved"] = sha(directory / asset["path"]) == fixture_sha
        if not all(checks.values()):
            report["error"] = "Failed checks: " + ", ".join(name for name, ok in checks.items() if not ok)
    except Exception as error:
        report["error"] = str(error)
        checks["completed_without_fixture_or_native_error"] = False
        if isinstance(error, subprocess.TimeoutExpired):
            report["timeout_seconds"] = error.timeout
            for name, value in (("native.stdout", error.stdout), ("native.stderr", error.stderr)):
                if value is not None:
                    (output / name).write_bytes(value.encode() if isinstance(value, str) else value)
        elif isinstance(error, subprocess.CalledProcessError):
            report["subprocess_stderr"] = str(error.stderr)[-3000:]
    finally:
        if server is not None:
            server.shutdown(); server.server_close()
        if thread is not None:
            thread.join(timeout=1)
        if store is not None:
            store.shutdown()
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["passed"] = bool(checks) and all(checks.values()) and "error" not in report
    (output / "production-download-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New evidence directory; never reuse a prior gate directory")
    args = parser.parse_args()
    try:
        report = run(args.source, args.binary, args.output)
        print(json.dumps({"passed": report["passed"], "checks": report["checks"], "error": report.get("error"),
                          "report": str(args.output.absolute() / "production-download-report.json"),
                          "elapsed_seconds": report["elapsed_seconds"]}, indent=2))
        return 0 if report["passed"] else 1
    except Exception as error:
        print(json.dumps({"passed": False, "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
