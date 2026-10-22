"""TAPNext integrity/admission tests and an explicitly enabled real model gate."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

import tapnext_runtime as runtime
import install_tapnext as installer
from learned_tracking import validate_recipe


class TAPNextTests(unittest.TestCase):
    def test_official_checkpoint_and_independent_point_recipe_are_pinned(self):
        lock, digest = runtime.load_lock()
        self.assertEqual(lock["models"]["tapnext"]["sha256"], "19de6b1495555c2afb4b56e823a3f3c2fd7236eea05c53d98feab3cccd1b4a28")
        self.assertEqual(len(digest), 64)
        self.assertTrue(any(item["size"] == 0 for item in lock["files"]))
        recipe = {"version": 1, "backend": "tapnext", "frame_start": 0, "frame_count": 2,
                  "points": [{"id": "center", "frame": 0, "x": .3, "y": .5}]}
        self.assertEqual(validate_recipe(recipe), recipe)
        for changed in ({**recipe, "backend": "tapnext-template"}, {**recipe, "command": "run"},
                        {**recipe, "frame_count": 33}, {**recipe, "points": []}):
            with self.assertRaises(ValueError):
                validate_recipe(changed)

    def test_actual_editor_validates_the_independent_recipe(self):
        source = Path(__file__).with_name("web") / "learned-tracking-ui.js"
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const sandbox={window:{}};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
const api=sandbox.window.CinematicumLearnedTracking;
const recipe={version:1,backend:'tapnext',frame_start:0,frame_count:2,points:[{id:'center',frame:0,x:.3,y:.5}]};
assert.equal(api.validateRecipe(recipe).backend,'tapnext');
assert.throws(()=>api.validateRecipe({...recipe,backend:'template'}));
'''
        result = subprocess.run([shutil.which("node"), "-e", script, str(source)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_inventory_detects_empty_changed_added_and_linked_source_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source/einops"
            source.mkdir(parents=True)
            empty = source / "__init__.py"
            empty.write_bytes(b"")
            model = root / "bootstapnext_ckpt.npz"
            model.write_bytes(b"INTEGRITY UNIT FIXTURE; NOT MODEL WEIGHTS")
            model_digest = hashlib.sha256(model.read_bytes()).hexdigest()
            lock = {"files": [{"path": "einops/__init__.py", "size": 0, "sha256": hashlib.sha256(b"").hexdigest()}],
                    "models": {"tapnext": {"name": model.name, "bytes": model.stat().st_size, "sha256": model_digest}}}
            with patch.object(runtime, "load_lock", return_value=(lock, "a" * 64)):
                self.assertEqual(runtime.verify_layout(root)["checkpoint"], model.resolve())
                empty.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "source differs"):
                    runtime.verify_layout(root)
                empty.write_bytes(b"")
                foreign = source / "foreign.py"
                foreign.write_text("untrusted")
                with self.assertRaisesRegex(ValueError, "inventory"):
                    runtime.verify_layout(root)
                foreign.unlink()
                empty.unlink()
                empty.symlink_to(model)
                with self.assertRaisesRegex(ValueError, "symbolic link"):
                    runtime.verify_layout(root)

    def test_missing_base_runtime_creates_no_download_or_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "TAPNext/cpu-v1"
            with patch("learned_tracking.find_learned_python", return_value=None), patch.object(installer, "default_destination", return_value=destination):
                with self.assertRaisesRegex(ValueError, "learned Torch"):
                    installer.install()
            self.assertFalse(destination.parent.exists())

    def test_existing_unverified_download_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            target = cache / "weights"
            target.write_bytes(b"preserve")
            record = {"name": target.name, "bytes": 8, "sha256": "0" * 64, "url": "https://example.invalid"}
            with patch.object(installer.urllib.request, "urlopen") as network:
                with self.assertRaises(ValueError):
                    installer.download(record, cache)
                network.assert_not_called()
            self.assertEqual(target.read_bytes(), b"preserve")

    def test_cancelled_publication_removes_only_its_owned_staging(self):
        from adapters import AdapterCancelled
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            destination = parent / "cpu-v1"
            checkpoint = parent / "unit-checkpoint"
            checkpoint.write_bytes(b"UNIT FIXTURE; NOT MODEL WEIGHTS")
            unrelated = parent / "keep"
            unrelated.write_text("preserved")
            event = threading.Event()
            digest = "a" * 64
            lock = {"sources": [{}], "packages": [{}], "models": {"tapnext": {"name": "weights"}}}
            def probe(directory, cancel_event):
                event.set()
                return {"available": True, "lock_sha256": digest, "checks": {"fixture": True}}
            with patch("learned_tracking.find_learned_python", return_value="/pinned/learned/python"), \
                    patch.object(installer, "default_destination", return_value=destination), \
                    patch.object(installer, "load_lock", return_value=(lock, digest)), \
                    patch.object(installer, "download", return_value=checkpoint), \
                    patch.object(installer, "unpack_source"), patch.object(installer, "probe", side_effect=probe):
                with self.assertRaises(AdapterCancelled):
                    installer.install(cancel_event=event)
            self.assertFalse(os.path.lexists(destination))
            self.assertEqual(list((parent / ".versions").iterdir()), [])
            self.assertEqual(unrelated.read_text(), "preserved")
            self.assertTrue(checkpoint.is_file())


@unittest.skipUnless(os.environ.get("CINEMATICUM_TAPNEXT_TEST") == "1", "Enable the installed official TAPNext checkpoint gate")
class ActualTAPNextTests(unittest.TestCase):
    def test_real_checkpoint_apply_persistence_invalidation_and_rendered_motion(self):
        import numpy as np
        from engine import render_project
        from learned_tracking import run_learned_tracking, point_application, verify_learned_source_files
        from server import Store
        with tempfile.TemporaryDirectory(prefix="cinematicum-TAPNext-ENGINE-TEST-") as temporary:
            root = Path(temporary)
            yy, xx = np.mgrid[:256, :256]
            base = np.stack([35 + (xx // 16) % 2 * 8, 47 + (yy // 16) % 2 * 8,
                             70 + (xx // 32 + yy // 32) % 2 * 9], axis=-1).astype(np.uint8)
            texture = np.random.default_rng(72351).integers(0, 256, (52, 52, 3), dtype=np.uint8)
            texture[:, :, 0] = 160 + texture[:, :, 0] // 3
            texture[:, :, 1:] //= 3
            frames = []
            for index in range(2):
                cx, cy = 75 + 14 * index, 135
                image = base.copy()
                mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= 24 ** 2
                region = image[cy-26:cy+26, cx-26:cx+26]
                local = mask[cy-26:cy+26, cx-26:cx+26]
                region[local] = texture[local]
                frames.append(image)
            source = root / "ENGINE_TEST_MOVING_DISK.mkv"
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", "256x256", "-r", "24", "-i", "pipe:0", "-an", "-c:v", "ffv1", "-level", "3",
                            "-pix_fmt", "bgr0", "-threads", "1", str(source)], input=np.stack(frames).tobytes(), check=True, timeout=5)
            store = Store(root / "workspace")
            try:
                project = store.new_project({"name": "ENGINE TEST TAPNext", "width": 256, "height": 256, "fps": 24})
                asset = store.admit(project["id"], source, source.name, {"fixture": "SYNTHETIC ENGINE TEST"})
                project = store.get(project["id"])
                project["clips"] = [{"id": "picture", "asset_id": asset["id"], "start": 0, "in": 0, "duration": 2, "track": 0}]
                project["settings"]["image_precision"] = "high16"
                project = store.save(project["id"], project)
                directory = store.project_dir(project["id"])
                original = hashlib.sha256(store.asset(project["id"], asset["id"])[1].read_bytes()).hexdigest()
                recipe = {"version": 1, "backend": "tapnext", "frame_start": 0, "frame_count": 2,
                          "points": [{"id": "center", "frame": 0, "x": 75/256, "y": 135/256}]}
                result = run_learned_tracking(project, directory, "picture", recipe, directory / "learned/outputs" / uuid.uuid4().hex)
                measured = result["measurement"]
                samples = measured["measurement"]["tracks"][0]["track"]["samples"]
                self.assertTrue(all(sample["visible"] for sample in samples))
                self.assertLess(max(math.hypot(s["x"]*256-(75+14*i), s["y"]*256-135) for i,s in enumerate(samples)), 3)
                plan = point_application(project, directory, "picture", measured, "center")
                project["clips"][0].update(tracking=plan["tracking"], learned_recipe=recipe, learned_bindings=[plan["binding"]])
                saved = store.save(project["id"], project)
                self.assertEqual(saved["clips"][0]["learned_bindings"][0]["backend"], "tapnext")
                verify_learned_source_files(saved, directory)
                changed = copy.deepcopy(saved)
                changed["clips"][0]["reverse"] = True
                changed = store.save(project["id"], changed)
                self.assertIn("invalidated", changed["clips"][0]["learned_bindings"][0])
                saved["revision"] = changed["revision"]
                restored = store.save(project["id"], saved)
                self.assertNotIn("invalidated", restored["clips"][0]["learned_bindings"][0])
                movie = root / "ENGINE_TEST_STABILIZED.mkv"
                render_project(restored, directory, movie, "master16")
                decoded = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(movie), "-threads", "1",
                                          "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"], capture_output=True, check=True, timeout=5).stdout
                pictures = np.frombuffer(decoded, dtype=np.uint8).reshape(2, 256, 256, 3).astype(np.float32)
                centers = []
                for picture in pictures:
                    foreground = (picture[:, :, 0] > 140) & (picture[:, :, 0] > picture[:, :, 1]*1.5) & (picture[:, :, 0] > picture[:, :, 2]*1.5)
                    ys, xs = np.nonzero(foreground)
                    self.assertGreater(len(xs), 1000)
                    centers.append((float(xs.mean()), float(ys.mean())))
                self.assertLess(math.dist(*centers), 1.5)
                self.assertEqual(hashlib.sha256(store.asset(project["id"], asset["id"])[1].read_bytes()).hexdigest(), original)
                store.shutdown()
                store = Store(root / "workspace")
                reopened = store.get(project["id"])
                self.assertEqual(reopened["clips"][0]["learned_recipe"]["backend"], "tapnext")
                self.assertNotIn("invalidated", reopened["clips"][0]["learned_bindings"][0])
            finally:
                store.shutdown()
