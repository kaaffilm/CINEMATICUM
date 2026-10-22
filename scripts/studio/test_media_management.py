"""Decoded proxies, source identity, relink preservation and API acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

from media_management import create_proxy, digest_file, inventory, proxy_file, relink_original
from engine import probe_media, render_project
from server import Store


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "real FFmpeg required")
class MediaManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cinematicum-proxy-TEST-")
        self.root = Path(self.temp.name)
        (self.root / "media").mkdir()
        self.source = self.root / "media" / "original.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x128:rate=30000/1001",
                        "-f", "lavfi", "-i", "sine=frequency=700:sample_rate=48000", "-frames:v", "18", "-t", "0.6006",
                        "-c:v", "libx264", "-threads", "1", "-c:a", "aac", str(self.source)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.asset = {"id": "original", "name": "ENGINE TEST source", "path": "media/original.mp4",
                      "sha256": digest_file(self.source), "size": self.source.stat().st_size, **probe_media(self.source)}
        self.project = {"version": 1,"id": "project", "name": "ENGINE TEST", "fps": 30000/1001,
                        "frame_rate": {"numerator": 30000,"denominator":1001}, "width": 160, "height": 128,
                        "assets": [self.asset], "clips": [{"id":"clip","asset_id":"original","start":0,"in":0,"duration":18,"track":0}],
                        "titles": [],"tracks":[],"settings":{},"revision":1}

    def tearDown(self):
        self.temp.cleanup()

    def test_proxy_actual_frame_cadence_and_original_retention(self):
        before=self.source.read_bytes();result=create_proxy(self.project,self.root,"original",640)
        self.assertEqual(result["frames"],18)
        self.assertLessEqual(result["relative_timestamp_error_seconds"],.000002)
        path,receipt=proxy_file(self.project,self.root,"original",640)
        self.assertEqual(digest_file(path),receipt["sha256"])
        self.assertEqual(self.source.read_bytes(),before)
        self.assertEqual(self.asset["path"],"media/original.mp4")
        self.assertEqual(inventory(self.project,self.root)["assets"][0]["proxies"][0]["frames"],18)
        self.assertTrue(create_proxy(self.project,self.root,"original",640)["cached"])

    def test_proxy_variable_frame_timestamps(self):
        variable=self.root/"media"/"vfr.mkv"
        subprocess.run(["ffmpeg","-v","error","-y","-i",str(self.source),"-an","-vf",
                        "select='not(mod(n,3))',setpts=PTS-STARTPTS","-fps_mode","vfr","-c:v","ffv1",str(variable)],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        a={"id":"vfr","name":"ENGINE TEST variable cadence","path":"media/vfr.mkv","sha256":digest_file(variable),
           "size":variable.stat().st_size,**probe_media(variable)}
        self.project["assets"].append(a)
        result=create_proxy(self.project,self.root,"vfr",640)
        self.assertEqual(result["frames"],6)
        self.assertLessEqual(result["relative_timestamp_error_seconds"],.000002)

    def test_relink_preserves_edit_identity_and_rejects_wrong_bytes(self):
        selected=self.root/"selected.mp4";selected.write_bytes(self.source.read_bytes())
        original_project=copy.deepcopy(self.project)
        self.source.unlink()
        self.assertFalse(inventory(self.project,self.root)["assets"][0]["present"])
        result=relink_original(self.project,self.root,"original",selected)
        self.assertTrue(result["restored"])
        self.assertEqual(self.project,original_project)
        self.assertEqual(digest_file(self.source),self.asset["sha256"])
        selected.write_bytes(b"unrelated content")
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            relink_original(self.project,self.root,"original",selected)
        self.assertEqual(digest_file(self.source),self.asset["sha256"])

    def test_relink_retains_damaged_original_for_recovery(self):
        selected=self.root/"selected.mp4";selected.write_bytes(self.source.read_bytes())
        self.source.write_bytes(b"damaged original bytes")
        result=relink_original(self.project,self.root,"original",selected)
        self.assertTrue(result["restored"])
        self.assertEqual(digest_file(self.source),self.asset["sha256"])
        self.assertEqual(list((self.root/"relinked-originals").iterdir())[0].read_bytes(),b"damaged original bytes")

    def test_tampered_cache_and_cancel_are_not_success(self):
        result=create_proxy(self.project,self.root,"original",640)
        path,_=proxy_file(self.project,self.root,"original",640)
        path.write_bytes(b"x"*result["size"])
        with self.assertRaises(FileNotFoundError):proxy_file(self.project,self.root,"original",640)
        self.assertFalse(create_proxy(self.project,self.root,"original",640)["cached"])
        event=threading.Event();event.set()
        with self.assertRaises(Exception):create_proxy(self.project,self.root,"original",960,cancel_event=event)
        self.source.write_bytes(b"damaged source")
        with self.assertRaisesRegex(ValueError,"changed"):
            create_proxy(self.project,self.root,"original",640)

    def test_symlink_boundaries(self):
        selected=self.root/"selected.mp4";selected.write_bytes(self.source.read_bytes())
        self.source.unlink();self.source.symlink_to(selected)
        with self.assertRaisesRegex(ValueError,"symlink"):
            relink_original(self.project,self.root,"original",selected)

    def test_proxy_setting_does_not_change_export_frames_or_pcm(self):
        a=self.root/"before.mov";b=self.root/"after.mov"
        render_project(self.project,self.root,a,profile="prores")
        create_proxy(self.project,self.root,"original",640)
        self.project["settings"]["preview_proxies"]={"enabled":True,"long_edge":640}
        render_project(self.project,self.root,b,profile="prores")
        def decode(path,kind):
            return subprocess.check_output(["ffmpeg","-v","error","-i",str(path)]+(["-an","-f","rawvideo","-pix_fmt","rgb24"] if kind=="picture" else ["-vn","-f","s16le","-ac","2","-ar","48000"])+["-"])
        self.assertEqual(decode(a,"picture"),decode(b,"picture"))
        self.assertEqual(decode(a,"sound"),decode(b,"sound"))


if __name__ == "__main__":
    unittest.main()
