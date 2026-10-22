"""Real float EXR, OCIO, movie/audio and owned-workflow ENGINE TEST fixtures."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

try:
    import numpy as np
    import OpenEXR
    import PyOpenColorIO as ocio
    FLOAT_RUNTIME = True
except ImportError:
    FLOAT_RUNTIME = False
from engine import RenderCancelled, probe_media, render_project, validate_project
from frame_preview import render_frame
from float_movie import DEFAULTS, capabilities, verify_master_package
from image_worker import write_png16
from test_imaging import read_generated_png16


@unittest.skipUnless(FLOAT_RUNTIME and shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "Real NumPy/OpenEXR/OCIO and FFmpeg are required; use the isolated Imaging interpreter")
class FloatMovieTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="cinematicum-FLOAT32-ENGINE-TEST-")
        self.root=Path(self.temp.name);(self.root/"media").mkdir();(self.root/"exports").mkdir()
        self.config=ocio.Config.CreateFromBuiltinConfig(DEFAULTS["config"])

    def tearDown(self):self.temp.cleanup()

    def exr(self,name,rgb=(-.25,1.5,2),alpha=.6,pixels=None,premultiplied=False):
        pixels=np.full((24,32,4),(*rgb,alpha),dtype=np.float32) if pixels is None else np.asarray(pixels,dtype=np.float32)
        target=self.root/"media"/(name+".exr")
        with OpenEXR.File({"compression":OpenEXR.ZIP_COMPRESSION,"type":OpenEXR.scanlineimage,
                          "cinematicumAlpha":"premultiplied" if premultiplied else "straight","ocioColorSpace":"ACEScg"},{"RGBA":pixels}) as f:f.write(str(target))
        return self.asset(name,target)

    def asset(self,name,path):
        return {"id":name,"name":"ENGINE TEST "+name,"path":str(path.relative_to(self.root)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),**probe_media(path)}

    def project(self,*assets):
        return {"version":1,"id":"ENGINE_TEST_FLOAT","name":"ENGINE TEST ONLY — Float movie","fps":4,"width":32,"height":24,
                "assets":list(assets),"clips":[],"titles":[],"settings":{"image_precision":"float32","transparent_background":True,"float_color":copy.deepcopy(DEFAULTS)}}

    def clip(self,asset,ident="clip",**values):
        return {"id":ident,"asset_id":asset["id"],"track":0,"start":0,"in":0,"duration":4,"float_input_space":"ACEScg",**values}

    def master(self,p,name="master"):
        target=self.root/"exports"/(name+".zip");receipt=render_project(p,self.root,target,"master32")
        manifest=verify_master_package(target,validate_project(p,self.root))
        return target,receipt,manifest

    def pixels(self,target,frame=0):
        with zipfile.ZipFile(target) as z:
            dest=self.root/("read-%s-%d.exr"%(target.stem,frame));dest.write_bytes(z.read("frames/frame-%08d.exr"%frame))
        with OpenEXR.File(str(dest),separate_channels=True) as f:
            self.assertTrue(all(f.channels()[c].pixels.dtype==np.dtype("float32") for c in "RGBA"))
            return np.stack([f.channels()[c].pixels for c in "RGBA"],axis=-1),dict(f.header())

    def movie(self,name="video"):
        target=self.root/"media"/(name+".mkv")
        # Independent exact source values, four actual frames and a real 48 kHz tone.
        arrays=np.zeros((4,24,32,4),dtype="<u2");arrays[...,3]=65535
        for n,color in enumerate(((1000,8000,16000),(16000,4000,32000),(32000,16000,2000),(50000,32000,8000))):arrays[n,...,:3]=color
        result=subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-y","-threads","1","-filter_complex_threads","1",
            "-f","rawvideo","-pixel_format","rgba64le","-video_size","32x24","-framerate","4","-i","pipe:0",
            "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=1","-c:v","ffv1","-level","3","-pix_fmt","gbrap16le","-threads","1","-c:a","pcm_s16le",str(target)],input=arrays.tobytes(),capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode());return self.asset(name,target),arrays

    def test_actual_float_pixels_preserve_negative_superwhite_and_fractional_alpha(self):
        a=self.exr("values",(-.25,4,2),.37);p=self.project(a);p["clips"]=[self.clip(a)]
        target,r,m=self.master(p);pixels,header=self.pixels(target)
        np.testing.assert_allclose(pixels,np.broadcast_to(np.array((-.25,4,2,1),dtype=np.float32)*np.float32(.37),(24,32,4)),rtol=0,atol=1e-7)
        self.assertEqual(header["cinematicumAlpha"],"premultiplied");self.assertEqual(r["processing_bits"],32)
        self.assertFalse(m["rgb_clipped_in_compositor"]);self.assertGreater(m["linear_statistics"]["above_one_channels"],0)
        self.assertLess(m["linear_statistics"]["minimum"],0);self.assertEqual(m["audio"]["samples"],48000)

    def test_two_real_layers_match_independent_associated_source_over(self):
        a=self.exr("under",(-.25,1.5,2),.6);b=self.exr("over",(-1,3,.25),.35);p=self.project(a,b)
        p["clips"]=[self.clip(a,"under"),self.clip(b,"over",track=1)]
        target,_,_=self.master(p);pixels,_=self.pixels(target)
        expected=np.array([-.25,1.5,2])*.6*(1-.35)+np.array([-1,3,.25])*.35
        np.testing.assert_allclose(pixels[...,:3],np.broadcast_to(expected,(24,32,3)),rtol=2e-6,atol=1e-7)
        np.testing.assert_allclose(pixels[...,3],.35+.6*(1-.35),rtol=1e-6)

    def test_tiny_positive_premultiplied_alpha_is_not_discarded(self):
        a=self.exr("tiny",(4e-9,-1e-9,2e-9),1e-9,premultiplied=True);p=self.project(a);p["clips"]=[self.clip(a)]
        target,_,_=self.master(p);actual,_=self.pixels(target)
        np.testing.assert_allclose(actual[0,0],(4e-9,-1e-9,2e-9,1e-9),rtol=2e-6,atol=0)

    def test_input_and_output_ocio_are_real_and_bound_to_exact_config(self):
        a=self.exr("color",(.18,.4,.7),1);p=self.project(a);p["clips"]=[self.clip(a,float_input_space="Linear Rec.709 (sRGB)")]
        p["settings"]["float_color"]["output_space"]="ACES2065-1"
        target,_,m=self.master(p);pixels,header=self.pixels(target)
        expected=np.array([.18,.4,.7],dtype=np.float32);self.config.getProcessor("Linear Rec.709 (sRGB)","ACES2065-1").getDefaultCPUProcessor().applyRGB(expected)
        np.testing.assert_allclose(pixels[0,0,:3],expected,rtol=3e-6,atol=2e-7)
        self.assertEqual(header["ocioColorSpace"],"ACES2065-1")
        with zipfile.ZipFile(target) as z:self.assertEqual(hashlib.sha256(z.read("config.ocio")).hexdigest(),m["color"]["config_sha256"])

    def test_scene_linear_exposure_is_applied_without_clipping(self):
        a=self.exr("exposure",(-.5,2,8),1);p=self.project(a);p["clips"]=[self.clip(a,grade={"exposure":2})]
        target,_,_=self.master(p);pixels,_=self.pixels(target)
        np.testing.assert_array_equal(pixels[0,0],np.array((-2,8,32,1),dtype=np.float32))

    def test_animated_movie_multitrack_frames_and_audio_are_actual_media(self):
        a,source=self.movie();b=self.exr("overlay",(-1,2,1),.25);p=self.project(a,b)
        p["clips"]=[self.clip(a,"movie",float_input_space="Linear Rec.709 (sRGB)"),self.clip(b,"moving",track=1,scale=.5,keyframes=[{"frame":0,"x":-.25},{"frame":3,"x":.25}])]
        target,_,m=self.master(p);frames=[self.pixels(target,n)[0] for n in range(4)]
        self.assertTrue(all(not np.array_equal(frames[n],frames[n+1]) for n in range(3)))
        with zipfile.ZipFile(target) as z:(self.root/"mix.wav").write_bytes(z.read("mix.wav"))
        raw=subprocess.run([shutil.which("ffmpeg"),"-v","error","-i",str(self.root/"mix.wav"),"-f","f32le","-c:a","pcm_f32le","pipe:1"],capture_output=True,check=True,timeout=15).stdout
        samples=np.frombuffer(raw,dtype="<f4");self.assertEqual(len(samples),96000);self.assertGreater(float(np.max(np.abs(samples))),.02)
        self.assertEqual(m["sources"][0]["sha256"],a["sha256"])

    def test_transform_does_not_bleed_hidden_rgb_and_retains_float_values(self):
        rgba=np.zeros((24,32,4),dtype=np.float32);rgba[6:18,8:24]=(-2,4,1,.7)
        a=self.exr("clear",pixels=rgba);hidden=rgba.copy();hidden[hidden[...,3]==0,:3]=(500,-200,1000)
        b=self.exr("hidden",pixels=hidden);outputs=[]
        for asset in (a,b):
            p=self.project(asset);p["clips"]=[self.clip(asset,scale=.73,rotation=27,x=.07,y=-.04)]
            target,_,_=self.master(p,asset["id"]);outputs.append(self.pixels(target)[0])
        np.testing.assert_array_equal(*outputs);self.assertTrue(np.any((outputs[0][...,3]>0)&(outputs[0][...,3]<.7)))
        self.assertLess(float(outputs[0][...,:3].min()),0);self.assertGreater(float(outputs[0][...,:3].max()),1)

    def test_keyframes_and_trimmed_animation_domain_keep_their_frame_positions(self):
        a=self.exr("pose",(2,-1,.5),.8);p=self.project(a);p["clips"]=[self.clip(a,scale=.5,duration=2,animation_duration=4,animation_offset=2,keyframes=[{"frame":0,"x":-.25},{"frame":3,"x":.25}])]
        target,_,_=self.master(p);first=self.pixels(target,0)[0];last=self.pixels(target,1)[0]
        xx=np.arange(32);centers=[float((v[...,3].sum(axis=0)*xx).sum()/v[...,3].sum()) for v in (first,last)]
        # Point-sampled bilinear edges have 1/6 and 5/6 coverage at columns
        # 10 and 26; their independent discrete centroid is 18 + 1/3.
        self.assertAlmostEqual(centers[0],18+1/3,places=4);self.assertAlmostEqual(centers[1],23.5,places=4)

    def test_display_frame_uses_the_same_actual_ocio_view_after_linear_black_composite(self):
        a=self.exr("display",(.2,.5,2),.4);p=self.project(a);p["clips"]=[self.clip(a)]
        out=self.root/"preview.png";receipt=render_frame(p,self.root,1,out)
        actual=read_generated_png16(out);expected=np.array([.08,.2,.8],dtype=np.float32)
        self.config.getProcessor(ocio.DisplayViewTransform(src="ACEScg",display=DEFAULTS["display"],view=DEFAULTS["view"])).getDefaultCPUProcessor().applyRGB(expected)
        np.testing.assert_allclose(actual[:3],np.clip(expected,0,1),atol=1/65535);self.assertEqual(actual[3],1)
        self.assertEqual(receipt["processing_bits"],32);self.assertIn("ocio",receipt["pipeline"])

    def test_display_movie_profile_has_actual_audio_and_exact_frame_count(self):
        a,_=self.movie();p=self.project(a);p["clips"]=[self.clip(a,float_input_space="Linear Rec.709 (sRGB)")]
        out=self.root/"review.mp4";report=render_project(p,self.root,out,"preview");actual=probe_media(out)
        self.assertEqual(actual["frames"],4);self.assertTrue(actual["has_audio"]);self.assertEqual(report["processing_bits"],32)
        self.assertFalse(report["hdr_monitoring"]);self.assertEqual(report["profile"],"preview")

    def test_fractional_project_rate_preserves_exact_audio_sample_duration(self):
        a=self.exr("clock");p=self.project(a);p["frame_rate"]={"numerator":30000,"denominator":1001};p["fps"]=30000/1001;p["clips"]=[self.clip(a,duration=2)]
        _,r,m=self.master(p);self.assertEqual(m["audio"]["samples"],3203);self.assertEqual(m["frame_rate"],p["frame_rate"])

    def test_reversed_actual_movie_uses_the_selected_source_frames(self):
        a,source=self.movie();p=self.project(a);p["clips"]=[self.clip(a,float_input_space="Linear Rec.709 (sRGB)",reverse=True)]
        target,_,_=self.master(p)
        transform=self.config.getProcessor("Linear Rec.709 (sRGB)","ACEScg").getDefaultCPUProcessor()
        for frame in range(4):
            expected=(source[3-frame,0,0,:3].astype(np.float32)/65535).copy();transform.applyRGB(expected)
            np.testing.assert_allclose(self.pixels(target,frame)[0][12,16,:3],expected,rtol=3e-6,atol=2e-7)

    def test_track_gain_and_muted_picture_use_the_existing_actual_audio_mixer(self):
        a,_=self.movie();p=self.project(a);p["clips"]=[self.clip(a,float_input_space="Linear Rec.709 (sRGB)")]
        def pcm(target):
            with zipfile.ZipFile(target) as z:(self.root/"check-audio.wav").write_bytes(z.read("mix.wav"))
            raw=subprocess.run([shutil.which("ffmpeg"),"-v","error","-i",str(self.root/"check-audio.wav"),"-f","f32le","pipe:1"],capture_output=True,check=True,timeout=10).stdout
            return np.frombuffer(raw,dtype="<f4")
        full=pcm(self.master(p,"full-gain")[0]);p["tracks"]=[{"id":0,"gain":.25}]
        quarter=pcm(self.master(p,"quarter-gain")[0]);np.testing.assert_allclose(quarter,full*.25,atol=1e-7)
        p["tracks"][0]["mute"]=True;target,_,_=self.master(p,"muted")
        self.assertEqual(float(np.abs(pcm(target)).max()),0);np.testing.assert_array_equal(self.pixels(target)[0],0)

    def test_actual_raster_title_is_transformed_from_srgb_with_frame_fades(self):
        target=self.root/"media/title.png"
        write_png16(target,np.full((24,32,4),(.6,.2,.1,.5),dtype=np.float32),np)
        a=self.asset("title",target);p=self.project(a)
        p["titles"]=[{"id":"title","text":"ENGINE TEST","asset_id":a["id"],"start":0,"duration":4,"fade":2}]
        archive,_,_=self.master(p);expected=np.array((.6,.2,.1),dtype=np.float32)
        self.config.getProcessor("sRGB Encoded Rec.709 (sRGB)","ACEScg").getDefaultCPUProcessor().applyRGB(expected)
        np.testing.assert_array_equal(self.pixels(archive,0)[0],0)
        # The stored PNG16 alpha is round(.5 * 65535) / 65535.
        alpha=32768/65535
        np.testing.assert_allclose(self.pixels(archive,2)[0][12,16,:3],expected*alpha,atol=2e-5)
        np.testing.assert_allclose(self.pixels(archive,1)[0][12,16],self.pixels(archive,2)[0][12,16]*.5,atol=1e-7)

    def test_unsupported_operations_and_ambiguous_exr_input_are_refused(self):
        for change in (lambda p:p["clips"][0].update(effects={"blur":1}),lambda p:p["clips"][0].update(grade={"contrast":1.1}),
                       lambda p:p["clips"][0].pop("float_input_space"),lambda p:p["settings"]["float_color"].update(config="/tmp/untrusted.ocio")):
            a=self.exr("unsupported");p=self.project(a);p["clips"]=[self.clip(a)];change(p)
            with self.assertRaises(ValueError):validate_project(p,self.root)

    def test_unknown_ocio_space_and_view_fail_without_publishing_output(self):
        a=self.exr("unknown");p=self.project(a);p["clips"]=[self.clip(a,float_input_space="NOT_A_COLOR_SPACE")]
        with self.assertRaisesRegex(RuntimeError,"Unknown.*OCIO"):self.master(p)
        self.assertFalse((self.root/"exports/master.zip").exists())
        p["clips"][0]["float_input_space"]="ACEScg";p["settings"]["float_color"]["view"]="NOT_A_VIEW"
        with self.assertRaisesRegex(RuntimeError,"display view"):self.master(p)

    def test_source_mutation_and_package_tampering_are_detected(self):
        a=self.exr("bound");p=self.project(a);p["clips"]=[self.clip(a)]
        target,_,_=self.master(p)
        tampered=self.root/"tampered.zip"
        with zipfile.ZipFile(target) as original,zipfile.ZipFile(tampered,"w") as changed:
            for name in original.namelist():changed.writestr(name,b"tampered" if name=="frames/frame-00000000.exr" else original.read(name))
        with self.assertRaisesRegex(ValueError,"identity|hash mismatch"):verify_master_package(tampered)
        with (self.root/a["path"]).open("ab") as f:f.write(b"changed")
        with self.assertRaisesRegex(ValueError,"changed after media admission"):self.master(p,"changed")

    def test_cancellation_preserves_existing_outputs_and_source_media(self):
        a=self.exr("cancel");p=self.project(a);p["clips"]=[self.clip(a,duration=120)]
        output=self.root/"exports/cancel.zip";output.write_bytes(b"previous completed output")
        event=threading.Event()
        def progress(value):
            if value>0:event.set()
        with self.assertRaises(RenderCancelled):render_project(p,self.root,output,"master32",progress=progress,cancel_event=event)
        self.assertEqual(output.read_bytes(),b"previous completed output")
        self.assertEqual(hashlib.sha256((self.root/a["path"]).read_bytes()).hexdigest(),a["sha256"])
        self.assertEqual(list((self.root/"exports").glob(".cinematicum-float-*")),[])

    def test_runtime_absence_is_explicit(self):
        self.assertFalse(capabilities(python="/not/installed/python")["available"])

    def test_archive_roundtrip_preserves_float_settings_sources_and_complete_master(self):
        from project_archive import export_archive,import_archive
        a=self.exr("archive");p=self.project(a);p["clips"]=[self.clip(a)]
        target,report,_=self.master(p,"a"*32);normalized=validate_project(p,self.root)
        report["filename"]=target.name
        (self.root/"exports"/(target.stem+".json")).write_text(json.dumps({"result":report,"snapshot":normalized,"issuance_effect":"NONE"}))
        package=self.root/"portable.cinematicum.zip";export_archive(normalized,self.root,package)
        with zipfile.ZipFile(package) as z:
            self.assertIn("exports/"+target.name,z.namelist());self.assertEqual(z.read("exports/"+target.name),target.read_bytes())
            state=json.loads(z.read("project.json"));self.assertEqual(state["settings"]["image_precision"],"float32")
            self.assertEqual(state["clips"][0]["float_input_space"],"ACEScg")
            self.assertEqual(hashlib.sha256(z.read(a["path"])).hexdigest(),a["sha256"])
        restored_root=self.root/"restored";restored_root.mkdir()
        restored=import_archive(package,restored_root)
        restored_dir=restored_root/restored["id"]
        self.assertEqual(restored["settings"],normalized["settings"])
        self.assertEqual((restored_dir/"exports"/target.name).read_bytes(),target.read_bytes())
        again=restored_dir/"exports"/"restored-render.zip";render_project(restored,restored_dir,again,"master32")
        with zipfile.ZipFile(target) as original,zipfile.ZipFile(again) as rerendered:
            self.assertEqual(original.read("frames/frame-00000000.exr"),rerendered.read("frames/frame-00000000.exr"))

if __name__=="__main__":unittest.main()
