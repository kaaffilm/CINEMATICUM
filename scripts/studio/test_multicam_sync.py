"""Actual signal/media/render acceptance for the automatic multicamera candidate.

Every audiovisual fixture is independently generated synthetic ENGINE TEST
material. Missing NumPy/FFmpeg fails this module; no fake worker or skipped
optional result stands in for measured synchronization.
"""
import copy
from contextlib import contextmanager
from fractions import Fraction
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile

import numpy as np

import multicam_sync as sync
import multicam_sync_worker as worker
from engine import probe_media, render_project, validate_project
from editorial import apply_action
from timebase import project_rate


class CorrelationNumericsTests(unittest.TestCase):
    def test_fft_overlap_normalization_matches_independent_scalar_summation(self):
        first = [.13, -.5, .21, .73, -.02, .98, -.3, .47, .17]
        second = [.24, -.61, .82, .12, -.4, .2]
        lags, values, counts = worker.normalized_correlations(first, second, -5, 8, 3)
        for lag, actual, count in zip(lags, values, counts):
            pairs = [(first[index + int(lag)], second[index]) for index in range(len(second))
                     if 0 <= index + int(lag) < len(first)]
            self.assertEqual(int(count), len(pairs))
            if len(pairs) < 3:
                self.assertEqual(actual, 0)
                continue
            mx = sum(x for x, _ in pairs) / len(pairs); my = sum(y for _, y in pairs) / len(pairs)
            expected = sum((x - mx) * (y - my) for x, y in pairs) / math.sqrt(
                sum((x - mx) ** 2 for x, _ in pairs) * sum((y - my) ** 2 for _, y in pairs))
            self.assertAlmostEqual(float(actual), expected, places=12)

    def test_non_frame_offsets_survive_gain_polarity_filter_and_noise(self):
        rng = np.random.default_rng(43967)
        base = rng.normal(0, .14, 13 * sync.RATE)
        h = np.hanning(31); h /= h.sum(); base = np.convolve(base, h, "same")
        first = base[:10 * sync.RATE]
        second = -.7 * np.convolve(base[11819:10 * sync.RATE + 11819], [.1, .8, .1], "same") + .13 + rng.normal(0, .0008, len(first))
        result = worker.estimate_pair(first, second, 2 * sync.RATE)
        self.assertTrue(result["accepted"], result)
        self.assertEqual(result["lag_samples"], 11819)
        self.assertEqual(result["polarity"], -1)
        self.assertEqual(result["offset_spread_samples"], 0)
        swapped = worker.estimate_pair(second, first, 2 * sync.RATE)
        self.assertTrue(swapped["accepted"], swapped)
        self.assertEqual(swapped["lag_samples"], -11819)

    def test_silence_constant_periodicity_unrelated_and_short_overlap_refuse(self):
        rng = np.random.default_rng(974)
        n = 8 * sync.RATE
        tone = np.sin(np.arange(n) * (2 * np.pi * 440 / sync.RATE)) * .1
        cases = [(np.zeros(n), np.ones(n) * .3, "silent_or_constant"),
                 (tone, np.roll(tone, 91), "ambiguous_offset"),
                 (rng.normal(0, .1, n), rng.normal(0, .1, n), "weak_correlation"),
                 (rng.normal(0, .1, sync.RATE), rng.normal(0, .1, sync.RATE), "insufficient_overlap")]
        for first, second, expected in cases:
            with self.subTest(expected=expected):
                result = worker.estimate_pair(first, second, sync.RATE)
                self.assertFalse(result["accepted"])
                self.assertEqual(result["reason"], expected)

    def test_clock_drift_is_measured_and_refused_without_retiming(self):
        rng = np.random.default_rng(2477)
        base = rng.normal(0, .3, 14 * sync.RATE)
        h = np.hanning(151); h /= h.sum(); base = np.convolve(base, h, "same")
        count = 12 * sync.RATE; coordinates = np.arange(count) * 1.0001 + 2317
        target = np.interp(coordinates, np.arange(len(base)), base)
        result = worker.estimate_pair(base[:count], target, sync.RATE)
        self.assertFalse(result["accepted"], result)
        self.assertEqual(result["reason"], "inconsistent_clock_or_offset", result)
        self.assertGreater(result["offset_spread_samples"], worker.MAX_OFFSET_SPREAD)
        self.assertAlmostEqual(result["measured_drift_ppm"], 100, delta=8)

    def test_actual_numpy_probe_and_missing_runtime_are_explicit(self):
        actual = sync.sync_capabilities(sys.executable)
        self.assertTrue(actual["available"], actual)
        self.assertTrue(actual["runtime_operations_verified"])
        missing = sync.sync_capabilities("/missing-CINEMATICUM-runtime/python")
        self.assertFalse(missing["available"])
        self.assertEqual(missing["operations"], [])

    def test_worker_sample_and_fft_memory_bounds_and_nonfinite_refusal(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-sync-worker-BOUND-") as temporary:
            root = Path(temporary)
            records = []
            for index, value in enumerate((float("nan"), 0.)):
                path = root / f"samples_{index:02d}.f32le"
                path.write_bytes(np.asarray([value], dtype="<f4").tobytes())
                records.append({"asset_id": f"camera_{index}", "filename": path.name,
                                "start_sample": 0, "samples": 1, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            request = {"version": 1, "reference_asset_id": "camera_0", "sources": records,
                       "max_lag_samples": sync.RATE, "min_overlap_samples": sync.MIN_OVERLAP}
            with self.assertRaisesRegex(ValueError, "non-finite"):
                worker.analyze(request, root)
            request["sources"][0]["samples"] = sync.MAX_WINDOW + 1
            with self.assertRaisesRegex(ValueError, "Decoded samples"):
                worker.analyze(request, root)
            request["sources"][0]["samples"] = 1; request["sources"][0]["filename"] = "../outside.f32le"
            with self.assertRaisesRegex(ValueError, "owned file identity"):
                worker.analyze(request, root)
        values = np.zeros(2 ** 20 + 1)
        with self.assertRaisesRegex(ValueError, "FFT memory bound"):
            worker.normalized_correlations(values, values, -1, 1, 4)


class ActualMulticamMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise RuntimeError("Actual multicamera acceptance requires FFmpeg and FFprobe; no skipped media gate is accepted.")
        configured = os.environ.get("CINEMATICUM_SYNC_TEST_ROOT")
        cls.temporary = None if configured else tempfile.TemporaryDirectory(prefix="cinematicum-multicam-sync-ENGINE-TEST-")
        cls.root = Path(configured or cls.temporary.name).resolve()
        cls.root.mkdir(parents=True, exist_ok=False if configured else True)
        (cls.root / "media").mkdir(); (cls.root / "fixture-inputs").mkdir()
        cls.python = sys.executable; cls.count = 12 * sync.RATE
        rng = np.random.default_rng(866973)
        world = rng.normal(0, .17, 20 * sync.RATE)
        kernel = np.hanning(31); kernel /= kernel.sum(); world = np.convolve(world, kernel, "same")
        margin = 3 * sync.RATE
        cls.reference = world[margin:margin + cls.count].astype("<f4")
        cls.positive_offset, cls.negative_offset = 11819, -7517
        cls.positive = (.75 * np.convolve(world[margin + cls.positive_offset:margin + cls.positive_offset + cls.count], [.1, .8, .1], "same")
                        + .08 + rng.normal(0, .0007, cls.count)).astype("<f4")
        cls.negative = (-.85 * world[margin + cls.negative_offset:margin + cls.negative_offset + cls.count]
                        - .05 + rng.normal(0, .0006, cls.count)).astype("<f4")
        wrong = rng.normal(0, .1, (cls.count, 2)).astype("<f4")
        cls.make_camera("reference", [np.column_stack([cls.reference] * 2)], "red")
        cls.make_camera("positive", [np.column_stack([cls.positive] * 2)], "blue")
        cls.make_camera("negative", [np.column_stack([cls.negative] * 2)], "green")
        cls.make_camera("multi", [wrong, np.column_stack([wrong[:, 0], cls.positive])], "yellow")
        cls.make_camera("silence", [np.zeros((cls.count, 2), dtype="<f4")], "black")
        periodic = np.sin(np.arange(cls.count) * (2 * np.pi * 440 / sync.RATE)) * .12
        cls.make_camera("periodic_a", [np.column_stack([periodic] * 2)], "white")
        cls.make_camera("periodic_b", [np.column_stack([np.roll(periodic, 119)] * 2)], "gray")
        positions = margin + 2307 + np.arange(12 * 44100) * (sync.RATE / 44100)
        resampled = np.interp(positions, np.arange(len(world)), world).astype("<f4")
        cls.make_camera("resampled", [np.column_stack([resampled] * 2)], "cyan", sample_rate=44100)
        cls.assets = []
        for path in sorted((cls.root / "media").glob("*.mkv")):
            cls.assets.append({"id": path.stem, "name": path.stem, "path": f"media/{path.name}",
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **probe_media(path)})

    @classmethod
    def tearDownClass(cls):
        if cls.temporary:
            cls.temporary.cleanup()

    @staticmethod
    def ffmpeg(arguments, payload=None):
        return subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-threads", "1", "-filter_threads", "1", "-filter_complex_threads", "1"] + list(map(str, arguments)),
                              input=payload, capture_output=True, check=True, timeout=30)

    @classmethod
    def make_camera(cls, name, streams, color, sample_rate=48000):
        arguments = ["-f", "lavfi", "-i", f"color=c={color}:s=64x48:r=24:d=12"]
        for index, value in enumerate(streams):
            path = cls.root / "fixture-inputs" / f"{name}-{index}.f32le"
            path.write_bytes(np.asarray(value, dtype="<f4").tobytes())
            arguments += ["-f", "f32le", "-ar", sample_rate, "-ac", 2, "-i", path]
        arguments += ["-map", "0:v"]
        for index in range(len(streams)):
            arguments += ["-map", f"{index + 1}:a"]
        arguments += ["-t", "12", "-c:v", "ffv1", "-c:a", "pcm_f32le", cls.root / "media" / f"{name}.mkv"]
        cls.ffmpeg(arguments)

    def project(self, fps=24):
        return {"version": 1, "id": "actual_multicam_sync", "name": "ENGINE TEST measured synchronization",
                "fps": fps, "width": 64, "height": 48, "assets": copy.deepcopy(self.assets),
                "clips": [], "titles": [], "tracks": []}

    def recipe(self, names=("reference", "positive"), **changes):
        return {"version": 1, "angles": [{"asset_id": name, "channel": 0} for name in names],
                "reference_asset_id": names[0], "window_samples": self.count,
                "max_lag_samples": 2 * sync.RATE, "min_overlap_samples": sync.MIN_OVERLAP, **changes}

    def analyze(self, label, recipe=None, project=None, **options):
        p = project or self.project()
        return sync.run_multicam_sync(p, self.root, recipe or self.recipe(),
                                     self.root / "multicam-sync/outputs" / label, python=self.python, **options)

    def receipt_sha(self, result):
        return result["artifacts"]["receipt.json"]["sha256"]

    @contextmanager
    def actual_http_workspace(self, names=("reference", "multi")):
        from server import Server, Store
        previous = os.environ.get("CINEMATICUM_SYNC_PYTHON")
        os.environ["CINEMATICUM_SYNC_PYTHON"] = self.python
        with tempfile.TemporaryDirectory(prefix="cinematicum-sync-HTTP-ENGINE-TEST-") as temporary:
            store = Store(Path(temporary) / "workspace")
            project = store.new_project({"name": "ENGINE TEST actual camera synchronization", "fps": 24, "width": 64, "height": 48})
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True); thread.start()
            def request(method, path, body=None, token=True):
                headers = {"X-Cinematicum-Token": store.token} if token else {}
                if isinstance(body, dict):
                    body = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
                elif body is not None:
                    headers["Content-Type"] = "application/octet-stream"
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=45)
                try:
                    connection.request(method, path, body, headers); response = connection.getresponse()
                    status, received_headers, data = response.status, dict(response.getheaders()), response.read()
                finally:
                    connection.close()
                if received_headers.get("Content-Type", "").startswith("application/json"):
                    data = json.loads(data)
                return status, received_headers, data
            try:
                base = "/api/projects/" + project["id"]; assets = {}
                for name in names:
                    status, _, asset = request("POST", base + "/import?name=ENGINE_TEST_" + name + ".mkv", (self.root / "media" / (name + ".mkv")).read_bytes())
                    self.assertEqual(status, 201, asset); assets[name] = asset
                yield store, base, assets, request
            finally:
                server.shutdown(); server.server_close(); thread.join(); store.shutdown()
                if previous is None:
                    os.environ.pop("CINEMATICUM_SYNC_PYTHON", None)
                else:
                    os.environ["CINEMATICUM_SYNC_PYTHON"] = previous

    def http_recipe(self, assets, selected=True):
        recipe = self.recipe()
        recipe["angles"] = [{"asset_id": asset["id"], "channel": 0} for asset in assets.values()]
        recipe["reference_asset_id"] = next(iter(assets.values()))["id"]
        if selected and "multi" in assets:
            next(item for item in recipe["angles"] if item["asset_id"] == assets["multi"]["id"]).update(stream_index=2, channel=1)
        return recipe

    def http_wait(self, request, job):
        deadline = time.monotonic() + 45
        while job["state"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(.025)
            status, _, job = request("GET", "/api/jobs/" + job["id"])
            self.assertEqual(status, 200)
        return job

    def test_http_real_selected_channel_job_apply_undo_save_reopen_and_owned_downloads(self):
        with self.actual_http_workspace() as (store, base, assets, request):
            ident = base.rsplit("/", 1)[1]; before = store.get(ident)
            request_body = {"project": before, "recipe": self.http_recipe(assets)}
            status, _, caps = request("GET", "/api/multicam-sync-capabilities")
            self.assertEqual(status, 200); self.assertTrue(caps["runtime_operations_verified"])
            self.assertEqual(request("POST", base + "/multicam-sync", request_body, token=False)[0], 403)
            status, _, job = request("POST", base + "/multicam-sync", request_body)
            self.assertEqual(status, 202, job); self.assertEqual(job["kind"], "multicam-sync")
            job = self.http_wait(request, job); self.assertEqual(job["state"], "completed", job)
            result = job["result"]; self.assertTrue(result["accepted"])
            positive = next(item for item in result["analysis"]["angles"] if item["asset_id"] == assets["multi"]["id"])
            self.assertEqual(positive["offset_samples"], 11819)
            self.assertEqual(store.get(ident), before)
            durable = json.loads((store.root / "jobs" / (job["id"] + ".json")).read_bytes())
            self.assertEqual(durable["state"], "completed"); self.assertEqual(durable["result"]["output_id"], job["id"])
            for name, artifact in result["artifacts"].items():
                status, headers, downloaded = request("GET", artifact["url"])
                self.assertEqual(status, 200, downloaded)
                actual = (store.project_dir(ident) / artifact["path"]).read_bytes()
                self.assertEqual(json.loads(actual) if name.endswith(".json") else actual, downloaded)
                self.assertEqual(hashlib.sha256(actual).hexdigest(), artifact["sha256"])
                self.assertEqual(headers["ETag"], '"' + artifact["sha256"] + '"')
            status, _, candidate = request("POST", base + "/multicam-sync-apply", {"project": before, "output_id": job["id"],
                                          "receipt_sha256": self.receipt_sha(result), "start": 7, "track": 0})
            self.assertEqual(status, 200, candidate); self.assertEqual(store.get(ident), before)
            group = candidate["project"]["multicam_groups"][0]
            self.assertEqual(group["synchronization"]["angles"][0]["source_in_samples"], 11819)
            status, _, saved = request("PUT", base, candidate["project"]); self.assertEqual(status, 200, saved)
            status, _, reopened = request("GET", base); self.assertEqual(reopened["multicam_groups"], saved["multicam_groups"])
            # The complete pre-edit snapshot is one ordinary undo; a durable
            # source measurement remains independently available for redo.
            undo = copy.deepcopy(before); undo["revision"] = saved["revision"]
            status, _, undone = request("PUT", base, undo); self.assertEqual(status, 200, undone)
            self.assertEqual(undone["clips"], []); self.assertEqual(undone.get("multicam_groups", []), [])
            redo = copy.deepcopy(candidate["project"]); redo["revision"] = undone["revision"]
            status, _, redone = request("PUT", base, redo); self.assertEqual(status, 200, redone)
            self.assertEqual(redone["multicam_groups"], group and [group])
            self.assertEqual(request("PUT", base, saved)[0], 409)
            other = store.new_project({"name": "ENGINE TEST other owner", "width": 64, "height": 48})
            self.assertNotEqual(request("GET", result["artifacts"]["receipt.json"]["url"].replace(ident, other["id"]))[0], 200)
            self.assertNotEqual(request("GET", base + "/multicam-sync/outputs/" + job["id"] + "/project.json")[0], 200)

    def test_http_rejected_sound_and_cancellation_never_create_an_edit(self):
        with self.actual_http_workspace(("reference", "silence")) as (store, base, assets, request):
            ident = base.rsplit("/", 1)[1]; before = store.get(ident)
            body = {"project": before, "recipe": self.http_recipe(assets)}
            status, _, job = request("POST", base + "/multicam-sync", body); self.assertEqual(status, 202, job)
            job = self.http_wait(request, job); self.assertEqual(job["state"], "completed", job)
            self.assertFalse(job["result"]["accepted"])
            status, _, refusal = request("POST", base + "/multicam-sync-apply", {"project": before, "output_id": job["id"], "receipt_sha256": self.receipt_sha(job["result"])})
            self.assertEqual(status, 400, refusal); self.assertIn("rejected", refusal["error"])
            status, _, pending = request("POST", base + "/multicam-sync", body); self.assertEqual(status, 202)
            self.assertEqual(request("POST", "/api/jobs/" + pending["id"] + "/cancel", {})[0], 200)
            cancelled = self.http_wait(request, pending); self.assertEqual(cancelled["state"], "cancelled", cancelled)
            self.assertFalse((store.project_dir(ident) / "multicam-sync/outputs" / pending["id"]).exists())
            self.assertEqual(store.get(ident), before)

    def test_actual_sample_receipts_survive_portable_restore_and_reapply_without_job_database(self):
        from project_archive import export_archive, import_archive
        with self.actual_http_workspace() as (store, base, assets, request):
            ident = base.rsplit("/", 1)[1]; before = store.get(ident)
            status, _, job = request("POST", base + "/multicam-sync", {"project": before, "recipe": self.http_recipe(assets)})
            self.assertEqual(status, 202); job = self.http_wait(request, job); self.assertEqual(job["state"], "completed", job)
            result = job["result"]
            candidate = sync.apply_synchronization(before, store.project_dir(ident), job["id"], self.receipt_sha(result))["project"]
            saved = store.save(ident, candidate); archive = store.root / "ENGINE_TEST_sync.cinematicum.zip"
            export_archive(saved, store.project_dir(ident), archive)
            with zipfile.ZipFile(archive) as package:
                for name in sync.artifact_names(2):
                    self.assertIn("multicam-sync/outputs/" + job["id"] + "/" + name, package.namelist())
            restored = import_archive(archive, store.root / "projects"); restored_dir = store.project_dir(restored["id"])
            self.assertNotEqual(restored["id"], ident)
            self.assertEqual(restored["multicam_groups"], saved["multicam_groups"])
            reapplied = sync.apply_synchronization(restored, restored_dir, job["id"], self.receipt_sha(result), start=300)
            self.assertEqual(len(reapplied["project"]["multicam_groups"]), 2)
            source_pixels = self.ffmpeg(["-i", store.project_dir(ident) / assets["reference"]["path"], "-frames:v", 1, "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]).stdout
            rendered = store.root / "ENGINE_TEST_restored-sync.mov"
            render_project(restored, restored_dir, rendered, "prores")
            actual = self.ffmpeg(["-i", rendered, "-frames:v", 1, "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]).stdout
            self.assertGreater(actual[0], 200); self.assertLess(actual[2], 15); self.assertGreater(source_pixels[0], 200)
            for name, record in result["artifacts"].items():
                path, verified = sync.artifact(restored_dir, job["id"], name)
                self.assertEqual(verified["sha256"], record["sha256"])
                self.assertEqual(path.read_bytes(), (store.project_dir(ident) / record["path"]).read_bytes())
            receipt = restored_dir / "multicam-sync/outputs" / job["id"] / "receipt.json"
            receipt.write_bytes(receipt.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "receipt changed"):
                export_archive(restored, restored_dir, store.root / "ENGINE_TEST_tampered.cinematicum.zip")

    def test_three_actual_videos_measure_positive_negative_and_polarity_offsets(self):
        result = self.analyze("three_cameras", self.recipe(("reference", "positive", "negative")))
        self.assertTrue(result["accepted"], result["analysis"])
        measured = {item["asset_id"]: item for item in result["analysis"]["angles"]}
        self.assertEqual(measured["positive"]["offset_samples"], self.positive_offset)
        self.assertEqual(measured["negative"]["offset_samples"], self.negative_offset)
        self.assertEqual(measured["negative"]["polarity"], -1)
        for source in result["receipt"]["sources"]:
            sample = self.root / "multicam-sync/outputs/three_cameras" / source["sample_file"]
            self.assertEqual(sample.stat().st_size, source["samples"] * 4)
            self.assertEqual(hashlib.sha256(sample.read_bytes()).hexdigest(), source["sample_sha256"])
        self.assertEqual(result["receipt"]["project_rate"], {"numerator": 24, "denominator": 1})
        decoded = np.fromfile(self.root / result["artifacts"]["samples_00.f32le"]["path"], dtype="<f4")
        np.testing.assert_array_equal(decoded, self.reference)
        block = result["waveforms"]["sources"][0]["blocks"][0]
        independently_selected = decoded[block["start_sample"]:block["start_sample"] + block["samples"]].astype(np.float64)
        self.assertEqual(block["min"], float(independently_selected.min()))
        self.assertEqual(block["max"], float(independently_selected.max()))
        self.assertAlmostEqual(block["rms"], float(np.sqrt(np.mean(independently_selected ** 2))), places=12)

    def test_measured_worker_result_schema_refuses_changed_types_clocks_and_waveform_bindings(self):
        result = self.analyze("schema_actual")
        receipt = result["receipt"]; worker_hash = receipt["implementation_sha256"]["multicam_sync_worker.py"]
        mutations = (
            lambda a, w: a.update(version=True),
            lambda a, w: a["angles"][1].update(asset_id=a["angles"][0]["asset_id"]),
            lambda a, w: a["angles"][1].update(offset_samples=a["angles"][1]["offset_samples"] + 1),
            lambda a, w: a["angles"][1].update(polarity=True),
            lambda a, w: a["angles"][1]["window_checks"][0].update(lag_samples=50000),
            lambda a, w: a["common_overlap"]["source_starts"].update(positive=False),
            lambda a, w: w.update(channels=True),
            lambda a, w: w["sources"][0].update(sample_sha256="0" * 64),
            lambda a, w: w["sources"][0]["blocks"][0].update(samples=0),
            lambda a, w: w["sources"][0]["blocks"][0].update(rms=float("nan")),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                analysis, waves = copy.deepcopy(result["analysis"]), copy.deepcopy(result["waveforms"])
                mutate(analysis, waves)
                with self.assertRaises(ValueError):
                    sync.validate_measurement_result(analysis, waves, receipt["recipe"], receipt["sources"], worker_hash)

    def test_selected_nondefault_stream_and_channel_change_actual_matching(self):
        wrong = self.analyze("multi_wrong", self.recipe(("reference", "multi")))
        self.assertFalse(wrong["accepted"])
        recipe = self.recipe(("reference", "multi"))
        recipe["angles"][1].update(stream_index=2, channel=1)
        right = self.analyze("multi_selected", recipe)
        self.assertTrue(right["accepted"], right["analysis"])
        self.assertEqual(right["analysis"]["angles"][1]["offset_samples"], self.positive_offset)
        self.assertEqual(right["receipt"]["sources"][1]["stream_index"], 2)
        self.assertEqual(right["receipt"]["sources"][1]["channel"], 1)

    def test_actual_44100_hz_source_is_resampled_on_the_export_sample_clock(self):
        result = self.analyze("resampled_clock", self.recipe(("reference", "resampled")))
        self.assertTrue(result["accepted"], result["analysis"])
        self.assertLessEqual(abs(result["analysis"]["angles"][1]["offset_samples"] - 2307), 1)
        self.assertEqual(result["receipt"]["sources"][1]["recorded_sample_rate"], 44100)
        self.assertEqual(result["receipt"]["rate"], 48000)

    def test_different_exact_source_windows_recover_the_same_global_offset(self):
        recipe = self.recipe(window_samples=8 * sync.RATE, max_lag_samples=3 * sync.RATE)
        recipe["angles"][0]["start_sample"] = 12345
        recipe["angles"][1]["start_sample"] = 61237
        result = self.analyze("window_binding", recipe)
        self.assertTrue(result["accepted"], result["analysis"])
        self.assertEqual(result["analysis"]["angles"][1]["offset_samples"], self.positive_offset)
        self.assertEqual(result["waveforms"]["sources"][0]["start_sample"], 12345)
        self.assertEqual(sum(block["samples"] for block in result["waveforms"]["sources"][1]["blocks"]), 8 * sync.RATE)

    def test_sample_accurate_apply_cut_save_reopen_and_actual_render(self):
        original = self.project(); original_copy = copy.deepcopy(original)
        result = self.analyze("rendered_group", project=original)
        applied = sync.apply_synchronization(original, self.root, result["output_id"], self.receipt_sha(result), name="Measured cameras", start=7)
        p = applied["project"]; group = p["multicam_groups"][0]; first = p["clips"][0]
        self.assertEqual(original, original_copy)
        self.assertEqual(project_rate(p).samples_for_frames(group["angles"][0]["in"]), self.positive_offset)
        self.assertNotEqual(group["angles"][0]["in"], int(group["angles"][0]["in"]))
        cut_frame = first["start"] + 24
        cut = apply_action(p, "multicam_cut", {"clip_id": first["id"], "angle_id": group["angles"][1]["id"], "frame": cut_frame}, self.root)["project"]
        saved = self.root / "saved-synchronized-project.json"; saved.write_text(json.dumps(cut))
        reopened = validate_project(json.loads(saved.read_text()), self.root)
        self.assertEqual(reopened["multicam_groups"], p["multicam_groups"])
        self.assertEqual(reopened["clips"][1]["in"], 24)
        output = self.root / "actual-synchronized-cut.mov"
        render_project(reopened, self.root, output, "prores")
        pcm = np.frombuffer(self.ffmpeg(["-i", output, "-map", "0:a:0", "-ar", "48000", "-ac", "2", "-f", "f32le", "pipe:1"]).stdout, dtype="<f4").reshape(-1, 2)
        frames = first["duration"]
        expected = np.concatenate([np.zeros(7 * 2000), self.reference[self.positive_offset:self.positive_offset + 24 * 2000], self.positive[24 * 2000:frames * 2000]])
        self.assertEqual(len(pcm), len(expected))
        self.assertLess(float(np.max(np.abs(pcm[:, 0] - expected))), 1 / 32768 + 1e-6)
        self.assertLess(float(np.max(np.abs(pcm[:, 1] - expected))), 1 / 32768 + 1e-6)
        pixels = self.ffmpeg(["-i", output, "-map", "0:v:0", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]).stdout
        stride = 64 * 48 * 3
        self.assertGreater(pixels[(cut_frame - 1) * stride], 220)
        self.assertGreater(pixels[cut_frame * stride + 2], 220)
        # One candidate is the undo boundary. Restoring the untouched prior
        # snapshot removes only this edit; its measured artifacts remain owned.
        undone = validate_project(original_copy, self.root)
        self.assertEqual(undone["clips"], [])
        self.assertFalse(undone.get("multicam_groups"))
        self.assertTrue((self.root / result["artifacts"]["receipt.json"]["path"]).is_file())

    def test_fractional_project_rate_retains_exact_sample_offsets_after_reopen(self):
        p = self.project(29.97)
        result = self.analyze("rational_group", project=p)
        applied = sync.apply_synchronization(p, self.root, result["output_id"], self.receipt_sha(result), start=31)["project"]
        reopened = validate_project(json.loads(json.dumps(applied)), self.root)
        rate = project_rate(reopened)
        self.assertEqual(rate.fraction, Fraction(30000, 1001))
        self.assertEqual(rate.samples_for_frames(reopened["multicam_groups"][0]["angles"][0]["in"]), self.positive_offset)
        binding = reopened["multicam_groups"][0]["synchronization"]
        self.assertEqual(binding["project_rate"], {"numerator": 30000, "denominator": 1001})

    def test_silence_and_periodic_media_publish_rejection_and_apply_cannot_override(self):
        for label, cameras in (("silent_media", ("reference", "silence")), ("periodic_media", ("periodic_a", "periodic_b"))):
            with self.subTest(cameras=cameras):
                original = self.project(); saved = copy.deepcopy(original)
                result = self.analyze(label, self.recipe(cameras), original)
                self.assertFalse(result["accepted"])
                with self.assertRaisesRegex(ValueError, "rejected synchronization"):
                    sync.apply_synchronization(original, self.root, result["output_id"], self.receipt_sha(result))
                self.assertEqual(original, saved)

    def test_decoded_short_tail_cannot_pass_as_a_shared_sound_window(self):
        recipe = self.recipe(window_samples=6 * sync.RATE, max_lag_samples=sync.RATE)
        recipe["angles"][1]["start_sample"] = 11 * sync.RATE
        result = self.analyze("short_decoded_tail", recipe)
        self.assertEqual(result["receipt"]["sources"][1]["samples"], sync.RATE)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["analysis"]["angles"][1]["reason"], "insufficient_overlap")

    def test_actual_recorder_clock_drift_is_rejected_with_measured_spread(self):
        kernel = np.hanning(151); kernel /= kernel.sum()
        reference = np.convolve(self.reference.astype(np.float64), kernel, "same")
        drifted = np.interp(np.arange(len(reference)) * 1.0001 + 2317, np.arange(len(reference)), reference)
        self.make_camera("drift_reference", [np.column_stack([reference] * 2)], "pink")
        self.make_camera("drift_camera", [np.column_stack([drifted] * 2)], "orange")
        p = self.project()
        for name in ("drift_reference", "drift_camera"):
            path = self.root / "media" / (name + ".mkv")
            p["assets"].append({"id": name, "path": "media/" + path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **probe_media(path)})
        recipe = self.recipe(("drift_reference", "drift_camera"), window_samples=11 * sync.RATE, max_lag_samples=sync.RATE)
        result = self.analyze("actual_clock_drift", recipe, p)
        self.assertFalse(result["accepted"], result["analysis"])
        comparison = result["analysis"]["angles"][1]
        self.assertEqual(comparison["reason"], "inconsistent_clock_or_offset", comparison)
        self.assertGreater(comparison["offset_spread_samples"], worker.MAX_OFFSET_SPREAD)
        self.assertAlmostEqual(comparison["measured_drift_ppm"], 100, delta=8)

    def test_invalid_stream_channel_window_and_duplicate_sources_never_publish(self):
        normal = self.recipe()
        cases = []
        for key, value in (("window_samples", sync.MAX_WINDOW + 1), ("max_lag_samples", True), ("min_overlap_samples", 10), ("version", True), ("reference_asset_id", "foreign")):
            cases.append({**normal, key: value})
        for change in ({"stream_index": 0}, {"stream_index": 90}, {"channel": 2}, {"channel": True}, {"start_sample": -1}, {"path": "/etc/passwd"}):
            recipe = copy.deepcopy(normal); recipe["angles"][1].update(change); cases.append(recipe)
        repeated = copy.deepcopy(normal); repeated["angles"][1] = repeated["angles"][0]; cases.append(repeated)
        for index, recipe in enumerate(cases):
            with self.subTest(recipe=recipe), self.assertRaises(ValueError):
                self.analyze("invalid_" + str(index), recipe)
            self.assertFalse((self.root / "multicam-sync/outputs" / ("invalid_" + str(index))).exists())

    def test_foreign_paths_symlinks_and_existing_results_are_preserved(self):
        parent = self.root / "multicam-sync/outputs"; parent.mkdir(parents=True, exist_ok=True)
        existing = parent / "keep_existing"; existing.mkdir(); sentinel = existing / "owner.txt"; sentinel.write_text("keep this")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.analyze("keep_existing")
        self.assertEqual(sentinel.read_text(), "keep this")
        foreign = self.root / "foreign"; foreign.mkdir(); linked = parent / "linked"; linked.symlink_to(foreign, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.analyze("linked")
        self.assertEqual(list(foreign.iterdir()), [])
        with self.assertRaisesRegex(ValueError, "must belong|must use"):
            sync.run_multicam_sync(self.project(), self.root, self.recipe(), self.root / "../outside", python=self.python)
        linked_media = self.root / "media/linked-source.mkv"; linked_media.symlink_to(self.root / "media/positive.mkv")
        p = self.project(); next(asset for asset in p["assets"] if asset["id"] == "positive")["path"] = "media/linked-source.mkv"
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            self.analyze("source_link", project=p)

    def test_source_tamper_before_analysis_and_after_measurement_refuses_apply(self):
        p = self.project(); path = self.root / "media/tamper-owned.mkv"; original = (self.root / "media/positive.mkv").read_bytes()
        path.write_bytes(original + b"changed-source-bytes")
        next(asset for asset in p["assets"] if asset["id"] == "positive")["path"] = "media/tamper-owned.mkv"
        with self.assertRaisesRegex(ValueError, "changed since admission"):
            self.analyze("tamper_before", project=p)
        path.write_bytes(original)
        result = self.analyze("tamper_after", project=p)
        self.assertTrue(result["accepted"])
        path.write_bytes(original + b"changed-after-measurement")
        before = copy.deepcopy(p)
        with self.assertRaisesRegex(ValueError, "changed since admission"):
            sync.apply_synchronization(p, self.root, result["output_id"], self.receipt_sha(result))
        self.assertEqual(p, before)

    def test_source_mutation_during_actual_analysis_cannot_publish(self):
        p = self.project(); path = self.root / "media/midrun-owned.mkv"
        path.write_bytes((self.root / "media/positive.mkv").read_bytes())
        next(asset for asset in p["assets"] if asset["id"] == "positive")["path"] = "media/midrun-owned.mkv"
        mutated = []
        def progress(value):
            if value > .04 and not mutated:
                with path.open("ab") as stream:
                    stream.write(b"source-mutated-during-owned-job")
                mutated.append(True)
        with self.assertRaisesRegex(ValueError, "changed during synchronization"):
            self.analyze("changed_during", project=p, progress=progress)
        self.assertTrue(mutated)
        self.assertFalse((self.root / "multicam-sync/outputs/changed_during").exists())

    def test_source_mutation_between_hash_and_actual_probe_is_refused(self):
        # Inject at the real probe boundary; the actual media parser still runs.
        # Capturing the source stat only after this probe would bind new bytes
        # to the old admitted hash and must not be accepted.
        import engine
        p = self.project(); path = self.root / "media/probe-race-owned.mkv"
        path.write_bytes((self.root / "media/positive.mkv").read_bytes())
        next(asset for asset in p["assets"] if asset["id"] == "positive")["path"] = "media/probe-race-owned.mkv"
        actual_probe, mutated = engine.probe_media, []
        def mutate_after_real_probe(filename):
            result = actual_probe(filename)
            if Path(filename) == path:
                with path.open("ab") as output:
                    output.write(b"changed-at-real-probe-boundary")
                mutated.append(True)
            return result
        engine.probe_media = mutate_after_real_probe
        try:
            with self.assertRaisesRegex(ValueError, "changed while verifying"):
                sync._sources(sync.validate_sync_recipe(self.recipe(), p), p, self.root)
        finally:
            engine.probe_media = actual_probe
        self.assertEqual(mutated, [True])

    def test_delayed_recorded_track_origin_is_refused_before_a_false_picture_alignment(self):
        path = self.root / "media/track-origin-delay.mkv"
        self.ffmpeg(["-i", self.root / "media/positive.mkv", "-itsoffset", "0.25", "-i", self.root / "media/positive.mkv",
                     "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", path])
        project = self.project(); asset = next(item for item in project["assets"] if item["id"] == "positive")
        asset.update(probe_media(path), path="media/track-origin-delay.mkv", sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, "sound and picture start at different times"):
            self.analyze("delayed_track", project=project)
        self.assertFalse((self.root / "multicam-sync/outputs/delayed_track").exists())

    def test_aac_priming_and_nonzero_shared_container_origin_are_checked_on_decoded_pts(self):
        for label, options in (("shared_origin", ["-c", "copy", "-output_ts_offset", "3"]),
                               ("aac_priming", ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "256k"])):
            with self.subTest(label=label):
                suffix = ".mov" if label == "aac_priming" else ".mkv"
                path = self.root / "media" / (label + suffix)
                self.ffmpeg(["-i", self.root / "media/positive.mkv", *options, path])
                actual = probe_media(path)
                clock = sync._source_clock(path, actual["video_stream_index"], actual["audio_stream_index"])
                self.assertLessEqual(abs(Fraction(clock["audio_minus_video_samples"])), 1)
                if label == "shared_origin":
                    self.assertEqual(Fraction(clock["video"]["first_pts"]) * Fraction(clock["video"]["time_base"]), 3)

    def test_sample_receipt_and_project_clock_tamper_refuse_apply(self):
        result = self.analyze("tamper_receipt")
        p = self.project()
        with self.assertRaisesRegex(ValueError, "receipt.*changed"):
            sync.apply_synchronization(p, self.root, result["output_id"], "0" * 64)
        other = self.project(25)
        with self.assertRaisesRegex(ValueError, "exact project clock"):
            sync.apply_synchronization(other, self.root, result["output_id"], self.receipt_sha(result))
        pcm = self.root / result["artifacts"]["samples_01.f32le"]["path"]
        data = bytearray(pcm.read_bytes()); data[211] ^= 1; pcm.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "sample bytes changed"):
            sync.apply_synchronization(p, self.root, result["output_id"], self.receipt_sha(result))

    def test_persisted_sample_binding_rejects_shifted_angle_and_changed_rate(self):
        result = self.analyze("bound_group")
        p = sync.apply_synchronization(self.project(), self.root, result["output_id"], self.receipt_sha(result))["project"]
        altered = copy.deepcopy(p); altered["multicam_groups"][0]["angles"][0]["in"] += .25
        with self.assertRaisesRegex(ValueError, "source offset changed"):
            validate_project(altered, self.root)
        altered = copy.deepcopy(p); altered["frame_rate"] = {"numerator": 25, "denominator": 1}; altered["fps"] = 25
        with self.assertRaisesRegex(ValueError, "project clock changed"):
            validate_project(altered, self.root)

    def test_cancel_before_decode_and_during_owned_child_leave_no_published_result(self):
        event = threading.Event(); event.set()
        with self.assertRaises(InterruptedError):
            self.analyze("cancel_before", cancel_event=event)
        event.clear(); seen = []
        def progress(value):
            seen.append(value)
            if value >= .45:
                event.set()
        with self.assertRaises(InterruptedError):
            self.analyze("cancel_actual", cancel_event=event, progress=progress)
        self.assertTrue(any(value >= .45 for value in seen))
        self.assertFalse((self.root / "multicam-sync/outputs/cancel_actual").exists())
        self.assertFalse(list((self.root / "multicam-sync/outputs").glob(".cancel_actual-building-*")))
        # An actual owned long-running child proves process termination; it is
        # not a replacement audio worker or a substituted numerical result.
        event.clear(); pid_path = self.root / "owned-cancel-child.pid"
        code = "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(60)"
        timer = threading.Timer(.15, event.set); timer.start()
        try:
            with self.assertRaises(InterruptedError):
                sync._run([sys.executable, "-I", "-B", "-c", code, str(pid_path)], self.root / "owned-cancel-child.log", event, time.monotonic() + 5)
        finally:
            timer.cancel(); timer.join()
        self.assertTrue(pid_path.exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_path.read_text()), 0)

    def test_owned_process_timeout_terminates_the_actual_child(self):
        pid_path = self.root / "owned-timeout-child.pid"
        code = "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(60)"
        with self.assertRaises(TimeoutError):
            sync._run([sys.executable, "-I", "-B", "-c", code, str(pid_path)], self.root / "owned-timeout-child.log", threading.Event(), time.monotonic() + .15)
        self.assertTrue(pid_path.exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_path.read_text()), 0)


if __name__ == "__main__":
    unittest.main()
