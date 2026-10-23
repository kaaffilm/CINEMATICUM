"""Unit checks only: these tests do not execute CameraCtrl inference."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import camera_ctrl as camera
import camera_ctrl_worker as worker


def request():
    matrix = [[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
    return {"prompt":"A furnished room","coordinate_system":"opencv_w2c","world_unit":"metre","intrinsic_units":"pixels",
            "frames":[{"w2c":copy.deepcopy(matrix),"intrinsics":{"fx":256.,"fy":256.,"cx":192.,"cy":128.}} for _ in range(16)]}


class CameraConditioningTests(unittest.TestCase):
    def test_identity_rays_use_pixel_centres_and_moment_first(self):
        result = camera.conditioning(request())
        self.assertEqual(result["shape"],[1,6,16,256,384])
        centre = result["probes"][1]["plucker"]
        self.assertEqual(centre[:3],[0.,0.,0.])
        self.assertGreater(centre[3],0)
        self.assertGreater(centre[4],0)
        self.assertAlmostEqual(sum(v*v for v in centre[3:]),1.,places=12)

    def test_translation_is_relative_to_first_camera(self):
        value = request()
        for frame in value["frames"]:
            frame["w2c"][0][3] = -10.
        value["frames"][15]["w2c"][0][3] = -12.
        result = camera.conditioning(value)
        self.assertEqual(result["relative_c2w"][0],[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]])
        self.assertEqual(result["relative_c2w"][15][0][3],2.)
        ray = result["probes"][-2]["plucker"]
        self.assertAlmostEqual(ray[0],0.)
        self.assertAlmostEqual(ray[1],-2*ray[5])
        self.assertAlmostEqual(ray[2],2*ray[4])
        self.assertAlmostEqual(sum(a*b for a,b in zip(ray[:3],ray[3:])),0.)

    def test_roll_is_preserved_instead_of_guessed_from_target(self):
        value = request()
        value["frames"][15]["w2c"] = [[0.,1.,0.,0.],[-1.,0.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
        result = camera.conditioning(value)
        self.assertEqual(result["relative_c2w"][15][:2],[[0.,-1.,0.,0.],[1.,0.,0.,0.]])

    def test_frame_count_raster_and_unknown_conditions_rejected(self):
        for field,value in (("frames",request()["frames"][:15]),("width",512),("coordinate_system","z_up_target_fov"),("intrinsic_units","normalised"),("distortion",[0,0])):
            invalid = request()
            invalid[field] = value
            with self.assertRaises(ValueError):
                camera.validate_request(invalid)

    def test_nonfinite_and_reflected_rotations_rejected(self):
        for element in (float("nan"),2.,-1.):
            value = request()
            value["frames"][0]["w2c"][0][0] = element
            with self.assertRaises(ValueError):
                camera.validate_request(value)

    def test_explicit_asymmetric_intrinsics_preserved(self):
        value = request()
        value["frames"][2]["intrinsics"] = {"fx":300.,"fy":260.,"cx":190.,"cy":121.}
        self.assertEqual(camera.conditioning(value)["intrinsics"][2],[300.,260.,190.,121.])

    def test_sample_options_are_finite_bounded_integers(self):
        for field,value in (("steps",True),("seed",2**32),("fps",1.5),("guidance_scale",float("inf"))):
            invalid = request()
            invalid[field] = value
            with self.assertRaises(ValueError):
                camera.validate_request(invalid)


class OfflineBoundaryTests(unittest.TestCase):
    def test_preexisting_cancellation_never_launches_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            event = threading.Event()
            event.set()
            with patch.object(camera.subprocess,"Popen") as launch:
                with self.assertRaises(InterruptedError):
                    camera.infer({"python":sys.executable},request(),Path(directory)/"cancelled",cancel_event=event)
                launch.assert_not_called()

    def test_unbounded_timeout_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            for timeout in (float("nan"),float("inf"),True,0,21601):
                with patch.object(camera.subprocess,"Popen") as launch:
                    with self.assertRaises(ValueError):
                        camera.infer({"python":sys.executable},request(),Path(directory)/"invalid",timeout=timeout)
                    launch.assert_not_called()

    def test_mps_is_unavailable_without_model_or_network_access(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"doctor"
            result = camera.doctor({"python":sys.executable,"device":"mps"},output,timeout=10)
            self.assertFalse(result["available"])
            self.assertFalse(result["inference_executed"])
            evidence = json.loads((output/"result.json").read_text())
            self.assertIn("requires cuda:0",evidence["error"])

    def test_physical_weight_hash_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = b"unit-test-not-model-weights"
            (root/"weights.bin").write_bytes(data)
            entry = {"path":"weights.bin","bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
            self.assertEqual(worker._entry(entry,root),root/"weights.bin")
            invalid = dict(entry,path="../weights.bin")
            with self.assertRaises(ValueError):
                worker._entry(invalid,root)
            (root/"weights.bin").write_bytes(b"modified")
            with self.assertRaises(ValueError):
                worker._entry(entry,root)

    def test_pinned_source_snapshot_ignores_untracked_shadow_and_rejects_modified_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"source"
            root.mkdir()
            for name in ("inference.py","tools/merge_lora2unet.py",worker.CONFIG):
                path = root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text("# unit fixture\n")
            def git(*args):
                return subprocess.check_output(["git","-C",str(root),*args],stderr=subprocess.DEVNULL)
            git("init")
            git("add",".")
            git("-c","user.name=Unit Test","-c","user.email=unit@example.invalid","commit","-m","unit source fixture")
            commit = git("rev-parse","HEAD").decode().strip()
            (root/"shadow.py").write_text("raise RuntimeError('untracked source')")
            output = Path(directory)/"output"
            output.mkdir()
            with patch.object(worker,"UPSTREAM_COMMIT",commit):
                snapshot,identities = worker._source_snapshot(root,output)
                self.assertNotIn("shadow.py",identities)
                self.assertFalse((snapshot/"shadow.py").exists())
                (root/"inference.py").write_text("# modified fixture\n")
                other = Path(directory)/"other"
                other.mkdir()
                with self.assertRaises(ValueError):
                    worker._source_snapshot(root,other)
                original_tree = git("rev-parse",commit+"^{tree}").decode().strip()
                git("add","inference.py")
                changed_tree = git("write-tree").decode().strip()
                git("replace",original_tree,changed_tree)
                replaced = Path(directory)/"replaced"
                replaced.mkdir()
                with self.assertRaises(ValueError):
                    worker._source_snapshot(root,replaced)


if __name__ == "__main__":
    unittest.main()
