"""Boundary tests only; synthetic pixels are not checkpoint acceptance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import diffusionlight_standalone as dl
import diffusionlight_worker as worker


class DiffusionLightBoundaries(unittest.TestCase):
    def test_unavailable_is_not_inference(self):
        result = dl.doctor({})
        self.assertFalse(result["available"])
        self.assertFalse(result["inference_verified"])
        self.assertNotIn("inference_executed", result)

    def test_rejects_unsupported_or_ambiguous_options(self):
        for options in ({"algorithm": "placeholder"}, {"seed": True}, {"seed": -1}, {"seed": 2**32},
                        {"steps": 9}, {"steps": 101}, {"steps": 30.0}, {"download": True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                dl.options(options)
        self.assertEqual(dl.options(), {"algorithm": "iterative", "seed": 0, "steps": 30})
        self.assertEqual(dl.options({"algorithm": "normal", "seed": 2**32-1})["algorithm"], "normal")

    def test_offline_environment(self):
        with patch.dict(os.environ, {"PYTHONPATH": "/untrusted", "HF_ENDPOINT": "https://untrusted.invalid",
                                     "TRANSFORMERS_CACHE": "/untrusted", "HF_TOKEN": "secret"}):
            env = dl._environment()
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("HF_ENDPOINT", env)
        self.assertNotIn("HF_TOKEN", env)
        self.assertEqual(env["HF_HUB_OFFLINE"], "1")
        self.assertEqual(env["TRANSFORMERS_OFFLINE"], "1")

    def test_relative_inventory_paths_are_canonical(self):
        for path in ("../model.bin", "/model.bin", "weights/../model.bin", "./model.bin", "a//b", "a\\b", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                worker.relative(path)

    def test_regular_file_and_manifest_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "source"
            source.mkdir()
            manifest = root / "models.json"
            manifest.write_text("{}")
            python = root / "python"
            python.symlink_to(sys.executable)
            runtime = {"python": str(python), "upstream_root": str(source), "model_manifest": str(manifest),
                       "model_manifest_sha256": dl.digest(manifest), "device": "cpu"}
            self.assertEqual(dl.validate_runtime(runtime)["python"], str(python))
            with self.assertRaisesRegex(ValueError, "MPS"):
                dl.validate_runtime({**runtime, "device": "mps"})
            manifest.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, "trusted identity"):
                dl.validate_runtime(runtime)
            link = root / "linked.json"
            link.symlink_to(manifest)
            with self.assertRaises(ValueError):
                dl._path(link)

    def test_input_identity_and_existing_output_are_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "input.png"
            source.write_bytes(b"not image bytes; no model worker is started")
            output = root / "output"
            output.mkdir()
            with patch.object(dl, "_run") as run:
                with self.assertRaisesRegex(ValueError, "admitted SHA256"):
                    dl.infer({}, source, "0" * 64, output)
                (output / "prior-evidence").write_text("retain")
                with self.assertRaisesRegex(ValueError, "empty"):
                    dl.infer({}, source, dl.digest(source), output)
                run.assert_not_called()
            self.assertEqual((output / "prior-evidence").read_text(), "retain")

    def test_pre_cancel_does_not_start_a_worker(self):
        event = threading.Event()
        event.set()
        with patch.object(dl, "validate_runtime", return_value={}), patch.object(dl.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "before launch"):
                dl._run({}, {"command": "doctor"}, event)
            popen.assert_not_called()

    def test_failed_infer_retains_log_and_unknown_execution_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "input.png"
            source.write_bytes(b"not decoded: worker execution is replaced in this boundary test")
            output = root / "output"
            output.mkdir()
            def failed_worker(runtime, request, cancel_event, timeout, _stderr):
                _stderr.write(b"Retained synthetic worker diagnostic\n")
                dl._record_state(output, stage="checkpoint_inference", status="running",
                                 inference_started=True, inference_executed=None)
                raise RuntimeError("synthetic owned operation timeout")
            with patch.object(dl, "_run", side_effect=failed_worker):
                with self.assertRaisesRegex(RuntimeError, "synthetic owned operation timeout"):
                    dl.infer({}, source, dl.digest(source), output)
            state = json.loads((output / "progress.json").read_bytes())
            self.assertTrue(state["inference_started"])
            self.assertIsNone(state["inference_executed"])
            self.assertFalse(state["inference_completed"])
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["stage"], "checkpoint_inference")
            self.assertIn("Retained synthetic worker diagnostic", (output / "worker.log").read_text())
            self.assertIn("Controller failure", (output / "worker.log").read_text())

    def test_later_failure_preserves_completed_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            dl._record_state(root, stage="worker_initialization", status="pending")
            initial = json.loads((root / "progress.json").read_bytes())
            self.assertFalse(initial["inference_started"])
            self.assertFalse(initial["inference_executed"])
            self.assertFalse(initial["inference_completed"])
            dl._record_state(root, inference_started=True, inference_executed=None)
            dl._record_state(root, inference_executed=True, inference_completed=True, stage="exposure_merge")
            state = dl._record_state(root, status="failed", error="synthetic projection error")
            self.assertTrue(state["inference_executed"])
            self.assertTrue(state["inference_completed"])
            for value in (False, None):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "cannot be reset"):
                    dl._record_state(root, inference_executed=value)

    def test_worker_upstream_and_projection_failures_retain_exact_stage_evidence(self):
        # These substitute upstream modules only to test durable failure-state
        # boundaries. No checkpoint, source pipeline or model inference runs.
        from PIL import Image
        for fail_at in ("upstream", "projection"):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                output = root / "output"
                output.mkdir()
                source = root / "input.png"
                source.write_bytes(b"synthetic boundary-test input; normalization substituted")
                lora = root / "synthetic-lora.safetensors"
                lora.write_bytes(b"synthetic boundary-test bytes, never loaded")
                models = {name: {"root": str(root)} for name in ("sdxl", "controlnet_depth", "vae", "depth")}
                models["lora"] = {"path": str(lora)}
                def fake_main():
                    current = json.loads((output / "progress.json").read_bytes())
                    self.assertTrue(current["inference_started"])
                    self.assertIsNone(current["inference_executed"])
                    self.assertFalse(current["inference_completed"])
                    if fail_at == "upstream":
                        raise RuntimeError("synthetic upstream failure")
                    for ev in ("-00", "-25", "-50"):
                        for directory, size in (("raw", 1024), ("square", 256), ("control", 1024)):
                            target = output / "inpaint" / directory
                            target.mkdir(parents=True, exist_ok=True)
                            Image.new("RGB", (size, size), (128, 128, 128)).save(target / ("input_ev%s_seed0.png" % ev))
                argument = types.ModuleType("relighting.argument")
                argument.SD_MODELS, argument.CONTROLNET_MODELS, argument.VAE_MODELS = {}, {}, {}
                inpainter = types.ModuleType("relighting.inpainter")
                relighting = types.ModuleType("relighting")
                relighting.__path__ = []
                relighting.argument, relighting.inpainter = argument, inpainter
                fake_inpaint = types.SimpleNamespace(main=fake_main)
                def fake_projection(*args):
                    raise RuntimeError("synthetic projection failure")
                modules = {"torch": types.ModuleType("torch"), "inpaint": fake_inpaint,
                           "ball2envmap": types.SimpleNamespace(process_image=fake_projection),
                           "exposure2hdr": types.ModuleType("exposure2hdr"), "relighting": relighting,
                           "relighting.argument": argument, "relighting.inpainter": inpainter}
                def direct_worker(runtime, request, cancel_event, timeout, _stderr):
                    _stderr.write(b"Synthetic upstream substitute; no model executed\n")
                    return worker.infer({**request, "runtime": runtime}, root, {}, models, {})
                with patch.dict(sys.modules, modules), patch.object(worker, "normalize_image", return_value={}), \
                     patch.object(dl, "_run", side_effect=direct_worker):
                    with self.assertRaisesRegex(RuntimeError, "synthetic " + fail_at + " failure"):
                        dl.infer({"device": "cpu"}, source, dl.digest(source), output)
                state = json.loads((output / "progress.json").read_bytes())
                self.assertTrue(state["inference_started"])
                self.assertEqual(state["inference_executed"], None if fail_at == "upstream" else True)
                self.assertEqual(state["inference_completed"], fail_at == "projection")
                self.assertEqual(state["stage"], "checkpoint_inference" if fail_at == "upstream" else "spherical_projection")
                self.assertEqual(state["status"], "failed")
                self.assertIn("Synthetic upstream substitute", (output / "worker.log").read_text())

    @unittest.skipUnless(hasattr(os, "killpg"), "POSIX owned process group cleanup")
    def test_owned_group_is_stopped_after_its_leader_exits(self):
        # This actual short subprocess test runs no model or application. The
        # orphan writes a marker in its SIGTERM handler, proving group cleanup
        # reached the exact owned child after its leader had already exited.
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "child-terminated"
            child_code = ("import pathlib, signal, time; "
                          "signal.signal(signal.SIGTERM, lambda *args: "
                          "(pathlib.Path(" + repr(str(marker)) + ").write_text('terminated'), exit(0))); "
                          "print('ready', flush=True); time.sleep(30)")
            leader_code = ("import subprocess,sys; p=subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "], "
                           "stdout=subprocess.PIPE,text=True); assert p.stdout.readline().strip()=='ready'; print(p.pid,flush=True)")
            process = subprocess.Popen([sys.executable, "-c", leader_code], stdout=subprocess.PIPE,
                                       text=True, start_new_session=True)
            try:
                child_pid = int(process.stdout.readline())
                process.wait(timeout=3)
                self.assertIsNotNone(process.returncode)
                dl._stop(process)
                self.assertEqual(marker.read_text(), "terminated")
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=3)
                process.stdout.close()

    def test_shipped_source_lock_and_known_lora_identity(self):
        path = Path(dl.__file__).with_name("diffusionlight-source-lock.json")
        self.assertEqual(dl.digest(path), dl.SOURCE_LOCK_SHA256)
        lock = json.loads(path.read_bytes())
        self.assertEqual(lock["commit"], "7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc")
        self.assertEqual(len(lock["files"]), 16)
        self.assertEqual(lock["lora"]["git_blob_sha1"], "8cfb0eb5ad164a8059f570434fcf2e7e051a06fe")

    def test_weight_inventory_detects_changes_and_extra_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            weights = root / "sdxl"
            weights.mkdir()
            weight = weights / "model.safetensors"
            weight.write_bytes(b"explicit synthetic unit-test payload, never loaded")
            entry = {"repository": "official/example", "revision": "1" * 40, "root": str(weights),
                     "files": [{"path": weight.name, "bytes": weight.stat().st_size, "sha256": dl.digest(weight)}]}
            lora = root / "lora.safetensors"
            lora.write_bytes(b"synthetic unit-test LoRA, not an actual checkpoint")
            manifest = root / "models.json"
            manifest.write_bytes(worker.encoded({"schema": "cinematicum-diffusionlight-models", "version": 1,
                                                "models": {"sdxl": entry, "lora": {"path": str(lora)}}}))
            runtime = {"model_manifest": str(manifest), "model_manifest_sha256": dl.digest(manifest)}
            lock = {"models": {"sdxl": "official/example"}, "lora": {"repository": "official/example",
                    "path": "official/checkpoint.safetensors", "size": lora.stat().st_size,
                    "git_blob_sha1": worker.blob_sha1(lora)}}
            self.assertEqual(worker.verify_models(runtime, lock)["lora"]["path"], str(lora))
            extra = weights / "unmanifested.bin"
            extra.write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "unmanifested"):
                worker.verify_models(runtime, lock)
            extra.unlink()
            weight.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "trusted manifest"):
                worker.verify_models(runtime, lock)

    def test_synthetic_hdr_numeric_validation_is_not_model_acceptance(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.exr"
            path.write_bytes(b"\x76\x2f\x31\x01synthetic header only; decoder replaced in this unit test")
            image = np.zeros((2, 4, 3), np.float32)
            image[0, 0] = 2
            fake = types.SimpleNamespace(imread=lambda _: image)
            with patch.dict(sys.modules, {"ezexr": fake}):
                values = worker.validate_hdr(path, height=2)
                self.assertEqual(values["maximum"], 2)
                for invalid in (np.full((2, 4, 3), np.nan, np.float32), np.full((2, 4, 3), -1, np.float32),
                                np.zeros((2, 4, 3), np.float32), np.zeros((2, 4, 3), np.float64), np.zeros((2, 4, 4), np.float32)):
                    image = invalid
                    with self.assertRaises(ValueError):
                        worker.validate_hdr(path, height=2)


if __name__ == "__main__":
    unittest.main()
