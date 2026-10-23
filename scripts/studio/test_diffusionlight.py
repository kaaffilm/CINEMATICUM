"""Fail-closed official DiffusionLight inference contract tests."""
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import diffusionlight as dl

def project(root):
    path=root/"source.png";data=b"ENGINE_TEST_SOURCE";path.write_bytes(data)
    return {"assets":[{"id":"source","kind":"image","path":"source.png","width":128,
                       "height":128,"size":len(data),"sha256":hashlib.sha256(data).hexdigest()}]}

class DiffusionLightTests(unittest.TestCase):
    def test_settings_and_source_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=project(root)
            r={"operation":"diffusionlight-hdr","settings":{"version":1,"asset_id":"source","seed":42,"exposures":[0,-2.5,-5]}}
            self.assertEqual(r,dl.validate_recipe(r,data))
            for v in ({"seed":-1},{"exposures":[0,-1,-4]},{"asset_id":"../etc/passwd"},{"version":True}):
                with self.assertRaises(ValueError):
                    dl.validate_settings({**r["settings"],**v})
            bad={**r,"operation":"render-placeholder"}
            with self.assertRaises(ValueError):dl.validate_recipe(bad,data)

    def test_no_checkpoint_is_no_inference(self):
        with mock.patch.dict("os.environ",{},clear=True):
            self.assertFalse(dl.capabilities()["available"])
            self.assertFalse(dl.capabilities()["actual_inference_accepted"])
            with self.assertRaises(RuntimeError):dl._runtime()

    def test_pre_cancel_preserves_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=project(root);e=threading.Event();e.set()
            r={"operation":"diffusionlight-hdr","settings":{"version":1,"asset_id":"source","seed":2,"exposures":[0,-2.5,-5]}}
            with self.assertRaises(InterruptedError):
                dl.run(p,root,r,root/"diffusionlight/outputs"/("f"*32),cancel_event=e)
            self.assertEqual(["source.png"],[x.name for x in root.iterdir()])

    def test_hdr_float_radiance_rejects_invalid_samples(self):
        import struct
        raw=struct.pack("<"+"f"*768,*([.25,.5,2.]*256))
        result=dl._validate_radiance(raw,16,16)
        self.assertEqual(768,result["decoded_rgb_samples"])
        self.assertEqual(2.,result["radiance_max"])
        with self.assertRaisesRegex(ValueError,"non-finite"):
            dl._validate_radiance(raw[:-4]+struct.pack("<f",float("nan")),16,16)
        with self.assertRaisesRegex(ValueError,"negative"):
            dl._validate_radiance(raw[:-4]+struct.pack("<f",-1),16,16)
        with self.assertRaisesRegex(ValueError,"exactly one"):
            dl._validate_radiance(raw[:-4],16,16)
        with self.assertRaisesRegex(ValueError,"entirely black"):
            dl._validate_radiance(bytes(len(raw)),16,16)

    def test_unexpected_exr_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"fake.exr";f.write_bytes(b"not-an-exr")
            with self.assertRaisesRegex(ValueError,"OpenEXR"):
                dl._probe_exr(f)

if __name__=="__main__":unittest.main()
