"""CameraCtrl tests: geometry proof and fail-closed actual inference admission."""
from __future__ import annotations
import copy
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import camera_ctrl as camera


def poses():
    return [{"intrinsics":[.75,.75,.5,.5],
             "w2c":[[1,0,0,i*.02],[0,1,0,0],[0,0,1,0]]}
            for i in range(camera.FRAMES)]


class CameraCtrlTests(unittest.TestCase):
    def recipe(self):
        return {"operation":"camera-conditioned-inference",
                "settings":{**camera.default_settings(),"prompt":"A cinematic corridor","poses":poses()}}

    def test_exact_model_input_and_pluecker_rays(self):
        validated=camera.validate_recipe(self.recipe(),{})
        self.assertEqual(camera.FRAMES,len(validated["settings"]["poses"]))
        rays=camera._center_rays(validated["settings"]["poses"])
        self.assertEqual([0,0,0,0,0,1],rays[0])
        self.assertAlmostEqual(.1,rays[5][1],places=8)
        bad=self.recipe()
        bad["settings"]["poses"][0]["w2c"][0][0]=2
        with self.assertRaisesRegex(ValueError,"orthonormal"):
            camera.validate_recipe(bad,{})
        bad=self.recipe()
        bad["settings"]["poses"][0]["w2c"][2][2]=-1
        with self.assertRaisesRegex(ValueError,"right-handed"):
            camera.validate_recipe(bad,{})
        bad=self.recipe()
        bad["settings"]["poses"][0]["intrinsics"][0]=-1
        with self.assertRaisesRegex(ValueError,"focal"):
            camera.validate_recipe(bad,{})

    def test_unapproved_model_never_claims_real_inference(self):
        with mock.patch.dict("os.environ",{},clear=True):
            capability=camera.capabilities()
            self.assertFalse(capability["available"])
            self.assertFalse(capability["inference_accepted"])
            with self.assertRaises(RuntimeError):
                camera._runtime()

    def test_cuda_failure_produces_no_admitted_movie(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            output=root/"camera-control/outputs"/("a"*32)
            config={"root":str(root)}
            with mock.patch.object(camera,"_runtime",return_value=(config,"f"*64,{})):
                with mock.patch.object(camera,"_execute",side_effect=RuntimeError("CUDA failure")):
                    with self.assertRaisesRegex(RuntimeError,"CUDA failure"):
                        camera.run({},root,self.recipe(),output)
            self.assertFalse(output.exists())

    def test_pre_cancel_cannot_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);event=threading.Event();event.set()
            with self.assertRaises(InterruptedError):
                camera.run({},root,self.recipe(),root/"camera-control/outputs"/("a"*32),
                           cancel_event=event)
            self.assertEqual([] ,list(root.iterdir()))


if __name__=="__main__":
    unittest.main()
