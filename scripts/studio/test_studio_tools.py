"""Actual EXR/HTTP/project/portable-artifact acceptance for studio tools."""
from __future__ import annotations

import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import zipfile

from server import Server, Store


def write_deep_fixture(path):
    """Two real depth samples per pixel, with a large UINT object identity."""
    import numpy as np
    import OpenEXR
    channels = {}
    for name, values in {"R": [.5, 0], "G": [0, 0], "B": [0, .5], "A": [.5, .5],
                         "Z": [1, 3], "ZBack": [1, 3], "objectID": [4_000_000_001, 4_000_000_002]}.items():
        pixels = np.empty((16, 16), dtype=object)
        dtype = np.uint32 if name == "objectID" else np.float32
        for y in range(16):
            for x in range(16):
                pixels[y, x] = np.array(values, dtype=dtype)
        channels[name] = pixels
    header = {"type": OpenEXR.deepscanline, "compression": OpenEXR.ZIPS_COMPRESSION,
              "name": "ENGINE_TEST_left", "view": "left"}
    OpenEXR.File(header, channels).write(str(path))


class StudioToolHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cinematicum-STUDIO-TOOL-TEST-")
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "workspace")
        self.project = self.store.new_project({"name": "ENGINE TEST studio tools", "width": 16, "height": 16})
        self.project_id = self.project["id"]
        self.base = "/api/projects/" + self.project_id
        self.server = Server(0, self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.shutdown()
        self.temp.cleanup()

    def request(self, method, path, body=None, token=True, content_type=None):
        headers = {}
        if token:
            headers["X-Cinematicum-Token"] = self.store.token
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        elif body is not None:
            headers["Content-Type"] = content_type or "application/octet-stream"
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=45)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            status, response_headers, data = response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()
        if response_headers.get("Content-Type", "").startswith("application/json"):
            data = json.loads(data)
        return status, response_headers, data

    def import_source(self):
        source = self.root / "ENGINE_TEST_depth.exr"
        write_deep_fixture(source)
        status, _, record = self.request("POST", self.base + "/deep-import?name=ENGINE_TEST_depth.exr", source.read_bytes())
        self.assertEqual(201, status, record)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), record["id"])
        return record

    def recipe(self, source_id):
        return {"version": 1, "nodes": [{"id": "source", "op": "source", "source_id": source_id}],
                "outputs": ["source"], "preview": {"output": 0, "channels": ["R", "G", "B"],
                                                        "alpha": "A", "exposure": 0, "transfer": "linear_to_srgb"}}

    def run_deep(self, recipe):
        return self.run_tool("deep-render", recipe)

    def run_tool(self, route, recipe):
        status, _, job = self.request("POST", self.base + "/" + route, {"recipe": recipe})
        self.assertEqual(202, status, job)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and job["state"] in {"queued", "running"}:
            time.sleep(.04)
            status, _, job = self.request("GET", "/api/jobs/" + job["id"])
            self.assertEqual(200, status)
        self.assertEqual("completed", job["state"], job)
        return job

    def test_actual_deep_import_job_download_media_and_graph_reopen(self):
        source = self.import_source()
        self.assertTrue(source["parts"][0]["deep"])
        self.assertEqual("left", source["parts"][0]["view"])
        recipe = self.recipe(source["id"])
        before = self.store.get(self.project_id)
        edited = copy.deepcopy(before)
        edited["deep_compositing"] = recipe
        status, _, saved = self.request("PUT", self.base, edited)
        self.assertEqual(200, status, saved)
        normalized = copy.deepcopy(saved["deep_compositing"])
        # One full project edit can be undone and reapplied through normal save.
        before["revision"] = saved["revision"]
        status, _, undone = self.request("PUT", self.base, before)
        self.assertEqual(200, status)
        self.assertNotIn("deep_compositing", undone)
        undone["deep_compositing"] = normalized
        self.assertEqual(200, self.request("PUT", self.base, undone)[0])
        self.assertEqual(normalized, self.request("GET", self.base)[2]["deep_compositing"])
        job = self.run_deep(normalized)
        result = job["result"]
        self.assertEqual({"composite.exr", "preview.png", "receipt.json"}, set(result["artifact_urls"]))
        status, headers, exr = self.request("GET", result["exr_url"])
        self.assertEqual(200, status)
        self.assertEqual(b"v/1\x01", exr[:4])
        self.assertIn("attachment", headers["Content-Disposition"])
        status, _, receipt = self.request("GET", result["receipt_url"])
        self.assertEqual(200, status)
        self.assertEqual(normalized, receipt["recipe"])
        self.assertEqual(hashlib.sha256(exr).hexdigest(), receipt["artifacts"]["exr"]["sha256"])
        status, _, preview = self.request("GET", result["display_url"])
        self.assertEqual(200, status)
        self.assertEqual(b"\x89PNG\r\n\x1a\n", preview[:8])
        asset = next(asset for asset in self.store.get(self.project_id)["assets"] if asset["id"] == result["asset"]["id"])
        self.assertEqual(hashlib.sha256(preview).hexdigest(), asset["sha256"])
        self.assertEqual("cinematicum-deep-compositing", asset["provenance"]["type"])
        from deep_compositing import list_deep_sources
        self.assertEqual([source], list_deep_sources(self.store.project_dir(self.project_id)))
        durable = json.loads((self.store.root / "jobs" / (job["id"] + ".json")).read_text())
        self.assertEqual("completed", durable["state"])
        self.assertEqual(receipt["recipe"], json.loads((self.store.root / "jobs" / (job["id"] + ".snapshot")).read_text())["recipe"])
        # Equal display pixels cannot collapse distinct scientific masters and
        # their receipts into an older asset with unrelated provenance.
        repeated = self.run_deep(normalized)["result"]
        self.assertNotEqual(asset["id"], repeated["asset"]["id"])
        self.assertEqual(asset["sha256"], repeated["asset"]["sha256"])
        self.assertNotEqual(asset["provenance"]["output_id"], repeated["asset"]["provenance"]["output_id"])

    def test_deep_sources_and_published_outputs_survive_archive_restore(self):
        from project_archive import export_archive, import_archive
        source = self.import_source()
        project = self.store.get(self.project_id)
        project["deep_compositing"] = self.recipe(source["id"])
        project = self.store.save(self.project_id, project)
        job = self.run_deep(project["deep_compositing"])
        project = self.store.get(self.project_id)
        archive = self.root / "ENGINE_TEST_deep.cinematicum.zip"
        export_archive(project, self.store.project_dir(self.project_id), archive)
        expected = {"deep/sources/" + source["id"] + suffix for suffix in (".json", ".exr")}
        expected |= {"deep/outputs/" + job["id"] + "/" + name for name in ("composite.exr", "preview.png", "receipt.json")}
        with zipfile.ZipFile(archive) as package:
            self.assertTrue(expected <= set(package.namelist()))
        restored = import_archive(archive, self.store.root / "projects")
        self.assertNotEqual(self.project_id, restored["id"])
        self.assertEqual(project["deep_compositing"], restored["deep_compositing"])
        original_dir, restored_dir = self.store.project_dir(self.project_id), self.store.project_dir(restored["id"])
        for relative in expected:
            self.assertEqual((original_dir / relative).read_bytes(), (restored_dir / relative).read_bytes())
        restored_url = job["result"]["exr_url"].replace(self.project_id, restored["id"])
        status, _, downloaded = self.request("GET", restored_url)
        self.assertEqual(200, status)
        self.assertEqual((restored_dir / "deep" / "outputs" / job["id"] / "composite.exr").read_bytes(), downloaded)
        history = self.request("GET", "/api/projects/" + restored["id"] + "/studio-results")[2]["results"]
        self.assertEqual([job["id"]], [row["output_id"] for row in history])
        self.assertEqual(restored_url, history[0]["artifact_urls"]["composite.exr"])
        # A reopened graph executes against the restored original, never the old path.
        from studio_tools import run_tool
        copied = run_tool(self.store, restored["id"], "deep-compositing", {"recipe": restored["deep_compositing"]})
        deadline = time.monotonic() + 30
        while copied["state"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(.04)
            copied = self.store.job(copied["id"])
        self.assertEqual("completed", copied["state"], copied)

    def test_mutations_require_token_and_invalid_documents_never_queue(self):
        for route in ("deep-render", "ray-optics", "physical-rendering"):
            self.assertEqual(403, self.request("POST", self.base + "/" + route, {"recipe": {}}, token=False)[0])
        self.assertEqual(400, self.request("POST", self.base + "/deep-render", {"recipe": {}})[0])
        self.assertFalse(self.store.jobs)
        bad = self.store.get(self.project_id)
        bad["deep_compositing"] = {"version": 1, "nodes": []}
        self.assertEqual(400, self.request("PUT", self.base, bad)[0])
        self.assertNotIn("deep_compositing", self.store.get(self.project_id))
        self.assertEqual(400, self.request("POST", self.base + "/deep-import?name=bad.py", b"arbitrary bytes")[0])
        self.assertEqual(400, self.request("POST", self.base + "/deep-import?name=bad.exr", b"not EXR")[0])

    def test_authoring_apply_rejects_without_mutation_then_commits_one_revision(self):
        source = self.import_source()
        before = self.store.get(self.project_id)
        body = {"tool": "deep-compositing", "document": self.recipe(source["id"]), "project": before}
        self.assertEqual(403, self.request("POST", self.base + "/authoring-apply", body, token=False)[0])
        broken = copy.deepcopy(body)
        broken["document"]["nodes"][0]["part"] = 99
        self.assertEqual(400, self.request("POST", self.base + "/authoring-apply", broken)[0])
        self.assertEqual(before, self.store.get(self.project_id))
        status, _, saved = self.request("POST", self.base + "/authoring-apply", body)
        self.assertEqual(200, status, saved)
        self.assertEqual(before["revision"] + 1, saved["revision"])
        self.assertEqual(source["id"], saved["deep_compositing"]["nodes"][0]["source_id"])
        # A stale dialog cannot overwrite an edit that has already committed.
        self.assertEqual(409, self.request("POST", self.base + "/authoring-apply", body)[0])
        self.assertEqual(saved, self.store.get(self.project_id))

    def test_artifact_ownership_and_download_allowlist(self):
        source = self.import_source()
        job = self.run_deep(self.recipe(source["id"]))
        other = self.store.new_project({"name": "Another project", "width": 16, "height": 16})
        copied_url = job["result"]["exr_url"].replace(self.project_id, other["id"])
        self.assertEqual(404, self.request("GET", copied_url)[0])
        self.assertEqual(400, self.request("GET", job["result"]["exr_url"].replace("composite.exr", "project.json"))[0])
        output = self.store.project_dir(self.project_id) / "deep" / "outputs" / job["id"] / "composite.exr"
        output.unlink()
        output.symlink_to(self.root / "ENGINE_TEST_depth.exr")
        self.assertEqual(400, self.request("GET", job["result"]["exr_url"])[0])

    def test_actual_optical_job_prescription_catalog_and_portable_outputs(self):
        from ray_optics import ARTIFACT_NAMES, default_prescription
        from project_archive import export_archive, import_archive
        status, _, capabilities = self.request("GET", "/api/ray-optics-capabilities")
        self.assertEqual(200, status)
        self.assertTrue(capabilities["available"], capabilities)
        status, _, catalog = self.request("GET", "/api/ray-optics-catalog?q=N-BK7&limit=10")
        self.assertEqual(200, status, catalog)
        self.assertIn("N-BK7", json.dumps(catalog))
        prescription = default_prescription()
        project = self.store.get(self.project_id)
        project["ray_optics"] = prescription
        status, _, saved = self.request("PUT", self.base, project)
        self.assertEqual(200, status, saved)
        self.assertEqual(saved["ray_optics"], self.request("GET", self.base)[2]["ray_optics"])
        recipe = {"version": 1, "operation": "analyze", "prescription": saved["ray_optics"],
                  "analysis": {"rings": 2, "fan_samples": 9, "pupil_samples": 16, "fft_grid": 64}}
        status, _, job = self.request("POST", self.base + "/ray-optics", {"recipe": recipe})
        self.assertEqual(202, status, job)
        deadline = time.monotonic() + 30
        while job["state"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(.05)
            job = self.request("GET", "/api/jobs/" + job["id"])[2]
        self.assertEqual("completed", job["state"], job)
        result = job["result"]
        self.assertEqual(set(ARTIFACT_NAMES), set(result["artifact_urls"]))
        self.assertNotIn("asset", result)
        measured = result["analysis"]["paraxial"]["effective_focal_length_mm"]
        n, thickness, first, second = 1.51680003, 5, 50, -50
        independent_efl = 1 / ((n - 1) * (1 / first - 1 / second + (n - 1) * thickness / (n * first * second)))
        self.assertAlmostEqual(independent_efl, measured, places=4)
        status, headers, rays = self.request("GET", result["artifact_urls"]["rays.csv"])
        self.assertEqual(200, status)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertGreater(len(rays.splitlines()), 10)
        self.assertEqual(hashlib.sha256(rays).hexdigest(), result["artifacts"]["rays.csv"]["sha256"])
        archive = self.root / "ENGINE_TEST_optics.cinematicum.zip"
        export_archive(self.store.get(self.project_id), self.store.project_dir(self.project_id), archive)
        restored = import_archive(archive, self.store.root / "projects")
        self.assertEqual(saved["ray_optics"], restored["ray_optics"])
        prefix = Path("optics") / "outputs" / job["id"]
        for name in ARTIFACT_NAMES:
            self.assertEqual((self.store.project_dir(self.project_id) / prefix / name).read_bytes(),
                             (self.store.project_dir(restored["id"]) / prefix / name).read_bytes())
        restored_url = result["artifact_urls"]["rays.csv"].replace(self.project_id, restored["id"])
        self.assertEqual(rays, self.request("GET", restored_url)[2])

    def test_actual_physical_render_float_master_media_and_portable_history(self):
        import numpy as np
        import OpenEXR
        from test_physical_rendering import fixture
        from project_archive import export_archive, import_archive
        scene, settings = fixture(16, 16)
        status, _, saved = self.request("POST", self.base + "/authoring-apply", {
            "tool": "physical-rendering", "document": settings, "scene": scene,
            "project": self.store.get(self.project_id)})
        self.assertEqual(200, status, saved)
        result = self.run_tool("physical-rendering", {"operation": "render", "settings": settings})["result"]
        self.assertEqual("cinematicum-physical-rendering", result["asset"]["provenance"]["type"])
        status, _, data = self.request("GET", result["artifact_urls"]["render.exr"])
        self.assertEqual(200, status)
        master = self.root / "ENGINE_TEST_physical.exr"
        master.write_bytes(data)
        with OpenEXR.File(str(master), separate_channels=True) as image:
            rgb = np.stack([image.channels()[name].pixels for name in ("R", "G", "B")], axis=-1)
        self.assertTrue(np.isfinite(rgb).all())
        # Independent Lambertian radiance: uniform unit environment returns rho.
        self.assertTrue(np.allclose(rgb.mean(axis=(0, 1)), [.2, .4, .6], atol=.035), rgb.mean(axis=(0, 1)))
        self.assertEqual(b"\x89PNG\r\n\x1a\n", self.request("GET", result["display_url"])[2][:8])
        archive = self.root / "ENGINE_TEST_physical.cinematicum.zip"
        export_archive(self.store.get(self.project_id), self.store.project_dir(self.project_id), archive)
        restored = import_archive(archive, self.store.root / "projects")
        self.assertEqual(settings, restored["physical_rendering"])
        restored_url = result["artifact_urls"]["render.exr"].replace(self.project_id, restored["id"])
        self.assertEqual(data, self.request("GET", restored_url)[2])
        history = self.request("GET", "/api/projects/" + restored["id"] + "/studio-results")[2]["results"]
        self.assertEqual("physical-rendering", history[0]["tool"])
        self.assertEqual(restored_url, history[0]["artifact_urls"]["render.exr"])

    def test_real_pbrt_import_preserves_resolution_and_requires_explicit_apply(self):
        from test_physical_rendering import fixture
        from physical_rendering import export_pbrt
        scene, settings = fixture(32, 24)
        before = self.store.get(self.project_id)
        result = self.run_tool("physical-rendering", {
            "operation": "pbrt_import", "settings": settings,
            "pbrt_text": export_pbrt(scene, settings)})["result"]
        self.assertEqual(before, self.store.get(self.project_id))
        self.assertEqual((32, 24), (result["scene"]["width"], result["scene"]["height"]))
        body = {"tool": "physical-rendering", "project": before,
                "scene": result["scene"], "document": result["settings"]}
        status, _, rejected = self.request("POST", self.base + "/authoring-apply", body)
        self.assertEqual(400, status, rejected)
        self.assertIn("resolution", json.dumps(rejected))
        self.assertEqual(before, self.store.get(self.project_id))
        body["project"] = {**before, "width": 32, "height": 24}
        status, _, saved = self.request("POST", self.base + "/authoring-apply", body)
        self.assertEqual(200, status, saved)
        self.assertEqual((32, 24), (saved["width"], saved["height"]))
        self.assertEqual(result["scene"], saved["settings"]["scene"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
