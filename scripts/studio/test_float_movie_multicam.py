"""Real combined FLOAT32 / locked-camera sound and source-mutation acceptance."""
import hashlib
import io
import shutil
import subprocess
import unittest
import zipfile

import engine
from editorial import apply_action
from float_movie import verify_master_package
import test_float_movie as fixtures


@unittest.skipUnless(fixtures.FLOAT_RUNTIME and hasattr(engine,"resolve_audio"),
                     "Use the combined multicamera engine and real isolated Imaging interpreter")
class FloatMovieMulticamTests(unittest.TestCase):
    def setUp(self):
        self.media=fixtures.FloatMovieTests();self.media.setUp();self.root=self.media.root
        sound,_=self.media.movie("locked_sound")
        silent_path=self.root/"media/silent_picture.mkv"
        subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-i",str(self.root/sound["path"]),
                        "-map","0:v:0","-c:v","copy","-an",str(silent_path)],check=True,capture_output=True,timeout=10)
        silent=self.media.asset("silent_picture",silent_path)
        inactive_path=self.root/"media/inactive_camera.mkv";shutil.copyfile(self.root/sound["path"],inactive_path)
        inactive=self.media.asset("inactive_camera",inactive_path)
        project=self.media.project(silent,sound,inactive)
        project=apply_action(project,"multicam_create",{"name":"ENGINE TEST three original cameras","start":0,"track":0,
            "angles":[{"asset_id":a["id"],"in":0} for a in (silent,sound,inactive)]},self.root)["project"]
        clip=project["clips"][0];clip["float_input_space"]="Linear Rec.709 (sRGB)"
        project=apply_action(project,"multicam_audio_lock",{"clip_id":clip["id"],"angle_id":project["multicam_groups"][0]["angles"][1]["id"],
            "stream_index":sound["audio_streams"][0]["index"],"channels":[0,0]},self.root)["project"]
        self.project=project;self.sources={a["id"]:a for a in (silent,sound,inactive)}

    def tearDown(self):self.media.tearDown()

    def master(self,name):
        target=self.root/"exports"/(name+".zip")
        report=engine.render_project(self.project,self.root,target,"master32")
        return target,report,verify_master_package(target,engine.validate_project(self.project,self.root))

    def decode_audio(self,path,channels=2):
        data=subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-i",str(path),"-map","0:a:0",
                             "-ar","48000","-ac",str(channels),"-c:a","pcm_f32le","-f","f32le","pipe:1"],
                            check=True,capture_output=True,timeout=10).stdout
        return fixtures.np.frombuffer(data,dtype="<f4").reshape(-1,channels)

    def test_silent_picture_uses_fixed_sound_and_master_binds_every_camera(self):
        self.assertFalse(self.sources["silent_picture"]["has_audio"])
        target,report,manifest=self.master("actual_locked_master")
        self.assertEqual({s["asset_id"] for s in manifest["sources"]},set(self.sources))
        self.assertEqual(manifest["audio"],{"sample_rate":48000,"channels":2,"samples":48000,"encoding":"pcm_f32le"})
        self.assertEqual(report["processing_bits"],32)
        with zipfile.ZipFile(target) as archive:(self.root/"actual-mix.wav").write_bytes(archive.read("mix.wav"))
        actual=self.decode_audio(self.root/"actual-mix.wav")
        # Explicit [0,0] mapping duplicates the original mono channel at unity;
        # FFmpeg's implicit mono-to-stereo layout conversion attenuates it.
        mono=self.decode_audio(self.root/self.sources["locked_sound"]["path"],channels=1)
        expected=fixtures.np.repeat(mono,2,axis=1)
        self.assertEqual(actual.shape,(48000,2));self.assertGreater(float(fixtures.np.abs(actual).max()),.02)
        fixtures.np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-7)

    def test_mutated_nonactive_locked_angle_blocks_float_export_and_preserves_completed_master(self):
        target,_,manifest=self.master("preserved")
        before=target.read_bytes();inactive=self.sources["inactive_camera"]
        self.assertNotIn(inactive["id"],{c["asset_id"] for c in self.project["clips"]})
        lock=self.project["multicam_groups"][0]["audio_lock"]
        sound_angle=next(a for a in self.project["multicam_groups"][0]["angles"] if a["id"]==lock["angle_id"])
        self.assertNotEqual(sound_angle["asset_id"],inactive["id"])
        with (self.root/inactive["path"]).open("ab") as stream:stream.write(b"ENGINE TEST altered nonactive camera bytes")
        # This exact real-source refusal must occur in the multicamera guard
        # before the Float32 early return or worker starts. No renderer mock.
        with self.assertRaisesRegex(ValueError,"multicamera source changed"):
            engine.render_project(self.project,self.root,target,"master32")
        self.assertEqual(target.read_bytes(),before)
        self.assertEqual(list((self.root/"exports").glob(".cinematicum-float-*")),[])
        for name in ("silent_picture","locked_sound"):
            asset=self.sources[name];self.assertEqual(hashlib.sha256((self.root/asset["path"]).read_bytes()).hexdigest(),asset["sha256"])
        self.assertEqual(verify_master_package(io.BytesIO(before))["sources"],manifest["sources"])


if __name__=="__main__":unittest.main()
