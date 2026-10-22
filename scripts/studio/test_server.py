"""HTTP and persistence tests. Any generated media here are test fixtures only."""
from __future__ import annotations
import copy
import http.client
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from server import Store, Server, ConflictError, WorkspaceInUseError


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory(prefix="cinematicum-http-test-fixtures-")
        cls.movie = Path(cls.fixtures.name) / "TEST_FIXTURE.mp4"
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=24:d=1", "-threads", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.movie)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cinematicum-server-tests-")
        self.store = Store(self.tmp.name)
        self.p = self.store.new_project({"name": "TEST PROJECT", "width": 160, "height": 90, "fps": 24})
        self.server = Server(0, self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.shutdown()
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None, token=True):
        headers = dict(headers or {})
        if token:
            headers["X-Cinematicum-Token"] = self.store.token
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=20)
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        status, rh, data = response.status, dict(response.getheaders()), response.read()
        connection.close()
        if rh.get("Content-Type", "").startswith("application/json"):
            data = json.loads(data)
        return status, rh, data

    def upload(self):
        status, _, asset = self.request("POST", f"/api/projects/{self.p['id']}/import?name=TEST_FIXTURE.mp4", self.movie.read_bytes(), {"Content-Type": "application/octet-stream"})
        self.assertEqual(201, status, asset)
        return asset

    def add_clip(self, asset):
        p = self.store.get(self.p["id"])
        p["clips"] = [{"id": "clip1", "asset_id": asset["id"], "start": 0, "in": 0, "duration": 24, "track": 0}]
        return p

    def test_every_editor_script_is_served_as_exact_shipped_javascript(self):
        sources = []
        class ScriptSources(HTMLParser):
            def handle_starttag(self, tag, attributes):
                source = dict(attributes).get("src") if tag == "script" else None
                if source:
                    sources.append(source)
        status, _, document = self.request("GET", "/", token=False)
        self.assertEqual(status, 200, document)
        parser = ScriptSources()
        parser.feed(document.decode("utf-8"))
        parser.close()
        self.assertTrue(sources, "The actual editor index must declare its scripts")
        for source in sources:
            with self.subTest(script=source):
                self.assertTrue(source.startswith("/") and not source.startswith("//"))
                self.assertNotIn("..", Path(source).parts)
                expected = (Path(__file__).parent / "web" / source[1:]).read_bytes()
                status, headers, actual = self.request("GET", source, token=False)
                self.assertEqual(status, 200, (source, actual))
                self.assertEqual(headers.get("Content-Type", "").split(";", 1)[0], "text/javascript")
                self.assertEqual(actual, expected, "HTTP must serve the exact shipped module")
                status, headers, body = self.request("HEAD", source, token=False)
                self.assertEqual(status, 200, source)
                self.assertEqual(int(headers["Content-Length"]), len(expected))
                self.assertEqual(body, b"")

    def test_managed_imaging_and_tracking_jobs_preserve_auth_lock_and_project_ownership(self):
        import runtime_management as runtime
        status, _, listing = self.request("GET", "/api/runtime-management")
        self.assertEqual(status, 200, listing)
        entries = {entry["id"]: entry for entry in listing["runtimes"]}
        before = (self.store.project_dir(self.p["id"]) / "project.json").read_bytes()
        for ident in ("imaging", "tracking"):
            with self.subTest(runtime=ident):
                entry = entries[ident]
                path = f"/api/projects/{self.p['id']}/runtime-management/{ident}"
                payload = {"operation": "check", "lock_sha256": entry["lock_sha256"]}
                self.assertEqual(self.request("POST", path, payload, token=False)[0], 403)
                self.assertEqual(self.request("POST", path, {**payload, "destination": "/tmp/injected"})[0], 400)
                self.assertEqual(self.request("POST", path, {**payload, "lock_sha256": "0" * 64})[0], 400)
                installer = runtime._installer(ident)
                result = {"status": "verified", "wheel_lock_sha256": entry["lock_sha256"]}
                with patch.object(installer, "install", return_value=result) as install:
                    status, _, job = self.request("POST", path, payload)
                    self.assertEqual(status, 202, job)
                    self.assertEqual(job["project_id"], self.p["id"])
                    self.assertEqual(job["kind"], "runtime-setup")
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline:
                        status, _, completed = self.request("GET", "/api/jobs/" + job["id"])
                        if completed["state"] not in ("queued", "running"):
                            break
                        time.sleep(.02)
                    self.assertEqual(completed["state"], "completed", completed)
                    self.assertEqual(completed["result"]["runtime_id"], ident)
                    self.assertEqual(completed["result"]["lock_sha256"], entry["lock_sha256"])
                    self.assertEqual(install.call_count, 1)
        self.assertEqual(before, (self.store.project_dir(self.p["id"]) / "project.json").read_bytes())

    def test_origin_host_token_and_json_are_required(self):
        path = "/api/projects"
        for headers, token in [({}, False), ({"Origin": "https://hostile.example"}, True), ({"Host": "hostile.example"}, True), ({"Sec-Fetch-Site": "cross-site"}, True)]:
            status, _, _ = self.request("POST", path, {"name": "bad"}, headers, token)
            self.assertEqual(403, status)
        status, _, _ = self.request("POST", path, b'{"name":"bad"}', {"Content-Type": "text/plain"})
        self.assertEqual(400, status)
        status, _, data = self.request("POST", path, {"name": "good"})
        self.assertEqual(201, status)
        self.assertEqual("good", data["name"])

    def test_lut_import_is_project_owned_and_only_applied_by_saved_clip(self):
        path = f"/api/projects/{self.p['id']}"
        before = (self.store.project_dir(self.p['id']) / "project.json").read_bytes()
        cube = 'TITLE "ENGINE TEST inverse"\nLUT_1D_SIZE 2\n1 1 1\n0 0 0\n'
        status, _, _ = self.request("POST", path + "/color-lut-import", {"text": cube}, token=False)
        self.assertEqual(403, status)
        status, _, imported = self.request("POST", path + "/color-lut-import", {"text": cube})
        self.assertEqual(201, status, imported)
        self.assertEqual(64, len(imported['lut']['sha256']))
        self.assertEqual(before, (self.store.project_dir(self.p['id']) / "project.json").read_bytes())
        status, _, listing = self.request("GET", path + "/color-luts")
        self.assertEqual(200, status)
        self.assertEqual([imported['lut']], listing['luts'])
        status, _, _ = self.request("POST", path + "/color-lut-import", {"path": "/etc/passwd"})
        self.assertEqual(400, status)
        asset = self.upload()
        project = self.add_clip(asset)
        project['clips'][0]['color_pipeline'] = {'version': 1, 'enabled': True,
            'lut': {'sha256': imported['lut']['sha256'], 'interpolation': 'linear'}}
        status, _, saved = self.request("PUT", path, project)
        self.assertEqual(200, status, saved)
        self.assertEqual(imported['lut']['sha256'], saved['clips'][0]['color_pipeline']['lut']['sha256'])
        owned = self.store.project_dir(self.p['id']) / 'color/luts' / (imported['lut']['sha256'] + '.cube')
        owned.write_text('tampered')
        status, _, error = self.request("PUT", path, saved)
        self.assertEqual(400, status, error)
        self.assertEqual(saved['revision'], self.store.get(self.p['id'])['revision'])

    def test_calibrated_camera_import_never_follows_image_names_or_autosaves(self):
        path = f"/api/projects/{self.p['id']}"
        before = (self.store.project_dir(self.p['id']) / "project.json").read_bytes()
        payload = {'format': 'colmap', 'cameras_text': '1 PINHOLE 160 90 100 110 85 40\n',
                   'images_text': '1 1 0 0 0 0 0 0 1 ../../not-a-local-file.jpg\n\n',
                   'scale': 1, 'up_axis': 'Z'}
        status, _, result = self.request('POST', path + '/scene/import-camera', payload)
        self.assertEqual(200, status, result)
        self.assertEqual(1, len(result['cameras']))
        camera = result['cameras'][0]['camera']
        self.assertAlmostEqual(100/110, camera['focal_ratio'])
        self.assertAlmostEqual(85/160-.5, camera['shift_x'])
        self.assertAlmostEqual(.5-40/90, camera['shift_y'])
        self.assertEqual(before, (self.store.project_dir(self.p['id']) / 'project.json').read_bytes())
        payload['cameras_text'] = '1 OPENCV 160 90 100 110 85 40 .1 .2 .3 .4\n'
        status, _, error = self.request('POST', path + '/scene/import-camera', payload)
        self.assertEqual(400, status, error)

    def test_mesh_candidate_job_owns_cancellation_and_never_autosaves(self):
        path = f"/api/projects/{self.p['id']}/scene/model-mesh"
        project_path = self.store.project_dir(self.p["id"]) / "project.json"
        before = project_path.read_bytes()
        started = threading.Event()
        def evaluate(payload, cancel_event=None):
            self.assertIsNotNone(cancel_event)
            started.set()
            if not cancel_event.wait(3):
                raise AssertionError("The Store did not deliver cancellation to its worker")
            raise RuntimeError("Mesh edit cancelled")
        payload = {"object": {"id": "owned"}, "operation": {"type": "convert"}}
        self.assertEqual(403, self.request("POST", path, payload, token=False)[0])
        self.assertEqual(400, self.request("POST", path, {**payload, "script": "arbitrary"})[0])
        with patch("scene_modeling.model_mesh", evaluate):
            status, _, job = self.request("POST", path, payload)
            self.assertEqual(202, status, job)
            self.assertEqual(job["kind"], "scene-modeling")
            self.assertTrue(started.wait(1))
            status, _, _ = self.request("POST", f"/api/jobs/{job['id']}/cancel", {})
            self.assertEqual(200, status)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                current = self.store.job(job["id"])
                if current["state"] not in {"queued", "running"}:
                    break
                time.sleep(.02)
            self.assertEqual(current["state"], "cancelled")
        self.assertEqual(before, project_path.read_bytes())

    def test_actual_imaging_http_preserves_master_and_admits_display_copy(self):
        import imaging
        from test_imaging import png16
        if not imaging.find_imaging_python():
            self.skipTest("An isolated imaging runtime is required for actual OCIO/EXR output")
        path = f"/api/projects/{self.p['id']}"
        fixture = Path(self.tmp.name) / "ENGINE_TEST_linear.png"
        png16(fixture, (.18, .09, .36))
        status, _, asset = self.request("POST", path + "/import?name=ENGINE_TEST_linear.png", fixture.read_bytes(), {"Content-Type": "application/octet-stream"})
        self.assertEqual(status, 201, asset)
        original = self.store.get(self.p["id"])
        status, _, catalog = self.request("GET", path + "/imaging-catalog")
        self.assertEqual(status, 200, catalog)
        recipe = {"version": 1, "operation": "ocio", "asset_id": asset["id"], "input_space": "ACEScg", "exposure": 1}
        self.assertEqual(403, self.request("POST", path + "/imaging-render", {"recipe": recipe}, token=False)[0])
        status, _, job = self.request("POST", path + "/imaging-render", {"recipe": recipe})
        self.assertEqual(status, 202, job)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            current = self.store.job(job["id"])
            if current["state"] not in {"queued", "running"}:
                break
            time.sleep(.05)
        self.assertEqual(current["state"], "completed", current)
        result = current["result"]
        for url in (result["url"], result["display_url"], result["exr_url"], result["receipt_url"]):
            status, _, data = self.request("GET", url)
            self.assertEqual(status, 200, (url, data))
        _, _, receipt = self.request("GET", result["receipt_url"])
        self.assertEqual(receipt["recipe"]["operation"], "ocio")
        directory = self.store.project_dir(self.p["id"])
        display = directory / "imaging" / "outputs" / job["id"] / "display.png"
        self.assertEqual(display.read_bytes(), (directory / result["asset"]["path"]).read_bytes())
        fresh = self.store.get(self.p["id"])
        self.assertEqual(fresh["revision"], original["revision"])
        self.assertEqual(fresh["clips"], original["clips"])
        self.assertEqual(len(fresh["assets"]), 2)
        self.assertEqual(self.request("GET", path + "/imaging/outputs/" + job["id"] + "/project.json")[0], 400)
        # Repeating an identical development may produce identical PNG bytes,
        # but its new asset must retain the matching master/receipt identity.
        status, _, repeated = self.request("POST", path + "/imaging-render", {"recipe": recipe})
        self.assertEqual(status, 202, repeated)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            repeated = self.store.job(repeated["id"])
            if repeated["state"] not in {"queued", "running"}:
                break
            time.sleep(.05)
        self.assertEqual(repeated["state"], "completed", repeated)
        repeat_asset = repeated["result"]["asset"]
        self.assertEqual(repeat_asset["sha256"], result["asset"]["sha256"])
        self.assertNotEqual(repeat_asset["id"], result["asset"]["id"])
        self.assertEqual(repeat_asset["provenance"]["output_id"], repeated["id"])
        self.assertEqual(self.store.get(self.p["id"])["clips"], original["clips"])
        # The float original is reusable, but cannot silently enter the SDR
        # timeline through the generic FFmpeg decoder.
        exr = (directory / "imaging" / "outputs" / job["id"] / "linear.exr").read_bytes()
        status, _, master = self.request("POST", path + "/import?name=ENGINE_TEST_master.exr", exr, {"Content-Type": "application/octet-stream"})
        self.assertEqual(status, 201, master)
        self.assertEqual(master["imaging_source"]["color_space"], "ACEScg")
        edit = self.store.get(self.p["id"])
        edit["clips"] = [{"id": "float", "asset_id": master["id"], "start": 0, "in": 0, "duration": 12, "track": 0}]
        status, _, error = self.request("PUT", path, edit)
        self.assertEqual(status, 400, error)
        self.assertIn("Develop this EXR", error["error"])

    def test_import_ranges_metadata_and_no_path_read(self):
        asset = self.upload()
        self.assertEqual("video", asset["kind"])
        self.assertEqual(64, len(asset["sha256"]))
        media = f"/api/projects/{self.p['id']}/media/{asset['id']}"
        status, h, data = self.request("GET", media, headers={"Range": "bytes=0-31"})
        self.assertEqual(206, status)
        self.assertEqual(self.movie.read_bytes()[:32], data)
        self.assertEqual("bytes", h["Accept-Ranges"])
        status, _, data = self.request("GET", media, headers={"Range": "bytes=-16"})
        self.assertEqual(self.movie.read_bytes()[-16:], data)
        status, _, _ = self.request("GET", media, headers={"Range": "bytes=999999999-"})
        self.assertEqual(416, status)
        status, _, _ = self.request("GET", "/api/projects/../media/etc/passwd")
        self.assertIn(status, (400, 404))
        status, _, _ = self.request("GET", "/../../etc/passwd")
        self.assertEqual(404, status)

    def test_save_reopen_and_conflict_preserve_changes(self):
        asset = self.upload()
        p = self.add_clip(asset)
        status, _, saved = self.request("PUT", f"/api/projects/{p['id']}", p)
        self.assertEqual(200, status, saved)
        self.assertGreater(saved["revision"], p["revision"])
        p["name"] = "Stale edit"
        status, _, _ = self.request("PUT", f"/api/projects/{p['id']}", p)
        self.assertEqual(409, status)
        self.store.shutdown()
        self.store = Store(self.tmp.name)
        self.server.store = self.store
        reopened = self.store.get(p["id"])
        self.assertEqual(24, reopened["clips"][0]["duration"])
        self.assertEqual("TEST PROJECT", reopened["name"])

    def test_registry_cannot_be_overwritten_by_project_payload(self):
        asset = self.upload()
        p = self.add_clip(asset)
        p["assets"] = [{**asset, "path": "/etc/passwd"}]
        saved = self.store.save(p["id"], p)
        self.assertEqual(asset["path"], saved["assets"][0]["path"])
        outside = Path(self.tmp.name) / "outside.mp4"
        shutil.copy2(self.movie, outside)
        actual = self.store.project_dir(p["id"]) / asset["path"]
        actual.unlink()
        actual.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.store.save(p["id"], saved)

    def test_invalid_import_leaves_no_admitted_file(self):
        status, _, _ = self.request("POST", f"/api/projects/{self.p['id']}/import?name=invalid.mp4", b"not media", {"Content-Type": "application/octet-stream"})
        self.assertEqual(400, status)
        self.assertEqual([], self.store.get(self.p["id"])["assets"])
        self.assertEqual([], list(self.store.project_dir(self.p["id"]).glob("upload-*")))

    def test_async_export_is_real_playable_media(self):
        asset = self.upload()
        p = self.add_clip(asset)
        status, _, job = self.request("POST", f"/api/projects/{p['id']}/render", {"project": p, "profile": "h264"})
        self.assertEqual(202, status, job)
        p["clips"][0]["duration"] = 1  # Render owns its snapshot.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            _, _, completed = self.request("GET", f"/api/jobs/{job['id']}")
            if completed["state"] not in {"queued", "running"}:
                break
            time.sleep(.05)
        self.assertEqual("completed", completed["state"], completed)
        self.assertAlmostEqual(1, completed["result"]["duration"], places=2)
        status, _, data = self.request("GET", completed["result"]["url"])
        self.assertEqual(200, status)
        self.assertGreater(len(data), 1000)
        report_path = self.store.project_dir(p["id"]) / "exports" / (job["id"] + ".json")
        self.assertEqual("NONE", json.loads(report_path.read_text())["issuance_effect"])

    def test_authoring_frame_is_real_cached_and_does_not_save_unsaved_edits(self):
        asset = self.upload()
        p = self.add_clip(asset)
        p["clips"][0]["grade"] = {"saturation": 0}
        route = f"/api/projects/{p['id']}/frame-preview"
        status, _, _ = self.request("POST", route, {"project": p, "frame": 4}, token=False)
        self.assertEqual(403, status)
        for cached in (False, True):
            status, _, job = self.request("POST", route, {"project": p, "frame": 4})
            self.assertEqual(202, status, job)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                _, _, completed = self.request("GET", f"/api/jobs/{job['id']}")
                if completed["state"] not in {"queued", "running"}:
                    break
                time.sleep(.03)
            self.assertEqual("completed", completed["state"], completed)
            result = completed["result"]
            self.assertEqual(4, result["frame"])
            self.assertEqual("timeline-export-graph", result["pipeline"])
            self.assertEqual(cached, result.get("cached", False))
            status, headers, picture = self.request("GET", result["url"])
            self.assertEqual(200, status)
            self.assertEqual(b"\x89PNG\r\n\x1a\n", picture[:8])
            self.assertFalse((self.store.root / "jobs" / (job["id"] + ".json")).exists())
        self.assertEqual([], self.store.get(p["id"])["clips"])
        status, _, _ = self.request("POST", route, {"project": p, "frame": 24})
        self.assertEqual(400, status)

    def test_rational_creation_and_data_only_mesh_import(self):
        status, _, project = self.request("POST", "/api/projects", {"name": "Rational", "width": 160, "height": 90, "frame_rate": {"numerator": 24000, "denominator": 1001}})
        self.assertEqual(201, status, project)
        self.assertEqual({"numerator": 24000, "denominator": 1001}, project["frame_rate"])
        self.assertAlmostEqual(24000/1001, project["fps"])
        route = f"/api/projects/{project['id']}/scene/import-obj"
        body = {"name": "ENGINE_TEST_triangle.obj", "obj": "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"}
        status, _, _ = self.request("POST", route, body, token=False)
        self.assertEqual(403, status)
        status, _, parsed = self.request("POST", route, body)
        self.assertEqual(200, status, parsed)
        self.assertEqual("mesh", parsed["objects"][0]["type"])
        self.assertEqual(project, self.store.get(project["id"]))
        status, _, _ = self.request("POST", "/api/projects", {"fps": 24, "frame_rate": {"numerator": 30000, "denominator": 1001}})
        self.assertEqual(400, status)

    def test_tracking_http_measures_snapshot_and_plans_without_saving(self):
        from test_tracking import TrackingTests
        TrackingTests.setUpClass()
        try:
            source = Path(self.tmp.name) / "ENGINE_TEST_tracking.mkv"
            shutil.copy2(TrackingTests.root / "media/moving.mkv", source)
            asset = self.store.admit(self.p["id"], source, source.name)
            project = self.add_clip(asset)
            base = f"/api/projects/{project['id']}"
            body = {"project": project, "clip_id": "clip1", "settings": {"frame_start": 0, "frame_count": 12, "x": 36/128, "y": 38/96, "radius": 8, "threshold": .1}}
            status, _, _ = self.request("POST", base+"/tracking", body, token=False)
            self.assertEqual(403, status)
            def complete(action):
                status, _, job = self.request("POST", base+action, body)
                self.assertEqual(202, status, job)
                deadline = time.monotonic()+10
                while time.monotonic()<deadline:
                    _, _, result = self.request("GET", "/api/jobs/"+job["id"])
                    if result["state"] not in {"queued", "running"}:
                        break
                    time.sleep(.03)
                self.assertEqual("completed", result["state"], result)
                return result
            seed = complete("/tracking-frame")
            status, _, png = self.request("GET", seed["result"]["url"])
            self.assertEqual((200, b"\x89PNG\r\n\x1a\n"), (status, png[:8]))
            self.assertFalse((self.store.root/"jobs"/(seed["id"]+".json")).exists())
            measured = complete("/tracking")
            track = measured["result"]["track"]
            self.assertTrue(all(point["visible"] for point in track["samples"]))
            status, _, planned = self.request("POST", base+"/tracking-motion", {"project": project, "clip_id": "clip1", "track": track})
            self.assertEqual(200, status, planned)
            self.assertEqual("stabilize", planned["motion"]["mode"])
            self.assertEqual([], self.store.get(project["id"])["clips"])
            wrong = copy.deepcopy(track); wrong["source"]["sha256"] = "0"*64
            status, _, _ = self.request("POST", base+"/tracking-validate", {"project": project, "clip_id": "clip1", "track": wrong})
            self.assertEqual(400, status)
            status, _, receipt = self.request("GET", measured["result"]["url"])
            self.assertEqual(200, status)
            self.assertEqual(track, receipt)
        finally:
            TrackingTests.tearDownClass()

    def test_waveform_uses_admitted_audio_and_bounded_sample_bins(self):
        source = Path(self.tmp.name) / "ENGINE_TEST_wave.wav"
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:sample_rate=48000:duration=0.25", str(source)], check=True)
        asset = self.store.admit(self.p["id"], source, source.name)
        route = f"/api/projects/{self.p['id']}/waveform/{asset['id']}"
        status, _, wave = self.request("GET", route + "?bins=32")
        self.assertEqual(200, status, wave)
        self.assertEqual(2, wave["channels"])
        self.assertEqual(12000, sum(wave["sample_counts"]))
        self.assertGreater(max(wave["peaks"][0]["max"]), .05)
        self.assertLess(min(wave["peaks"][0]["min"]), -.05)
        status, _, repeat = self.request("GET", route + "?bins=32")
        self.assertEqual(200, status)
        self.assertTrue(repeat["cached"])
        status, _, _ = self.request("GET", route + "?bins=999999")
        self.assertEqual(400, status)

    def test_atomic_automation_and_invalid_recipe(self):
        asset = self.upload()
        p = self.add_clip(asset)
        p = self.store.save(p["id"], p)
        status, _, changed = self.request("POST", f"/api/projects/{p['id']}/automate", {"project": p, "operations": [{"action": "grade", "values": {"saturation": 0}}, {"action": "volume", "value": 0}]})
        self.assertEqual(200, status, changed)
        self.assertEqual(0, changed["clips"][0]["grade"]["saturation"])
        status, _, _ = self.request("POST", f"/api/projects/{p['id']}/automate", {"project": changed, "operations": [{"action": "grade", "values": {"saturation": 2}}, {"action": "shell", "command": "ignored"}]})
        self.assertEqual(400, status)
        self.assertEqual(0, self.store.get(p["id"])["clips"][0]["grade"]["saturation"])

    def test_ui_workflow_is_rejected_and_bootstrap_has_capabilities(self):
        status, _, body = self.request("POST", f"/api/projects/{self.p['id']}/workflow", {"nodes": [], "links": []})
        self.assertEqual(400, status)
        with patch("server.check_comfyui", return_value={"available": False, "reason": "test server absent"}):
            status, _, body = self.request("GET", "/api/bootstrap")
        self.assertEqual(200, status)
        self.assertEqual(self.store.token, body["token"])
        self.assertEqual(False, body["capabilities"]["comfyui"]["available"])

    def test_source_trim_cannot_silently_reuse_measured_motion(self):
        asset = self.upload()
        project = self.add_clip(asset)
        project["clips"][0]["tracking"] = {"version": 1, "mode": "stabilize", "keys": [
            {"frame": 0, "x": 0, "y": 0}, {"frame": 23, "x": .1, "y": 0}]}
        project = self.store.save(project["id"], project)
        route = f"/api/projects/{project['id']}/automate"
        for trim in ({"in": 1, "duration": 20}, {"in": .5}):
            status, _, result = self.request("POST", route, {"project": project, "operations": [
                {"action": "grade", "values": {"saturation": 0}}, {"action": "trim", **trim}]})
            self.assertEqual(400, status, result)
            self.assertEqual(project, self.store.get(project["id"]))
        status, _, shortened = self.request("POST", route, {"project": project, "operations": [{"action": "trim", "duration": 20}]})
        self.assertEqual(200, status, shortened)
        self.assertEqual(project["clips"][0]["tracking"], shortened["clips"][0]["tracking"])


class WorkspaceLockTests(unittest.TestCase):
    """Exercise real OS process contention rather than mocking flock."""

    def other_process(self, workspace):
        program = """
import json, sys
from server import Store, WorkspaceInUseError
try:
    store = Store(sys.argv[1])
except WorkspaceInUseError as exc:
    print(json.dumps({"locked": True, "error": str(exc)}))
    raise SystemExit(73)
else:
    store.shutdown()
    print(json.dumps({"locked": False}))
"""
        result = subprocess.run([sys.executable, "-c", program, str(workspace)],
                                cwd=str(Path(__file__).resolve().parent), capture_output=True,
                                text=True, timeout=5)
        return result.returncode, json.loads(result.stdout)

    def test_second_process_cannot_recover_live_jobs_and_owner_releases(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-lock-tests-") as workspace:
            owner = Store(workspace)
            try:
                job_path = Path(workspace) / "jobs" / "owned-test-job.json"
                job_path.write_text(json.dumps({"id": "owned-test-job", "state": "running"}), encoding="utf-8")
                before = job_path.read_bytes()
                status, result = self.other_process(workspace)
                self.assertEqual(status, 73)
                self.assertTrue(result["locked"])
                self.assertIn("already in use", result["error"])
                self.assertEqual(job_path.read_bytes(), before, "Rejected process must not relabel a live job as interrupted")
            finally:
                owner.shutdown()
            owner.shutdown()  # Idempotent and must not affect the next owner.
            self.assertTrue((Path(workspace) / ".cinematicum-workspace.lock").is_file())
            status, result = self.other_process(workspace)
            self.assertEqual(status, 0)
            self.assertFalse(result["locked"])
            self.assertEqual(json.loads(job_path.read_text())["state"], "interrupted")

    def test_lock_remains_held_until_worker_finishes_shutdown(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-lock-worker-tests-") as workspace:
            owner = Store(workspace)
            started, cancellation_seen, allow_finish = threading.Event(), threading.Event(), threading.Event()

            def worker(job_id, progress, cancel):
                started.set()
                cancel.wait(timeout=5)
                cancellation_seen.set()
                allow_finish.wait(timeout=5)
                return {"fixture": "worker shutdown ordering test"}

            closer = None
            try:
                owner.submit("lock-test-project", "test", worker)
                self.assertTrue(started.wait(timeout=2))
                closer = threading.Thread(target=owner.shutdown)
                closer.start()
                self.assertTrue(cancellation_seen.wait(timeout=2))
                self.assertTrue(closer.is_alive())
                status, result = self.other_process(workspace)
                self.assertEqual(status, 73)
                self.assertTrue(result["locked"])
                allow_finish.set()
                closer.join(timeout=3)
                self.assertFalse(closer.is_alive())
                status, result = self.other_process(workspace)
                self.assertEqual(status, 0)
                self.assertFalse(result["locked"])
            finally:
                allow_finish.set()
                owner.shutdown()
                if closer is not None:
                    closer.join(timeout=1)

    def test_failed_initialization_releases_workspace_lock(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-lock-init-tests-") as workspace:
            obstruction = Path(workspace) / "projects"
            obstruction.write_text("Initialization failure test fixture", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                Store(workspace)
            obstruction.unlink()
            status, result = self.other_process(workspace)
            self.assertEqual(status, 0)
            self.assertFalse(result["locked"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
