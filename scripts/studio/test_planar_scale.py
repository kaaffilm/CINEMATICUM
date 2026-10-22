"""Resource and long-document contracts for bounded extended planar tracking."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from projective_warp import (COORDINATES, IDENTITY, MAX_PLANAR_FRAMES,
                             MAX_PLANAR_ANALYSIS_EDGE, MAX_PLANAR_DECODE_BYTES,
                             compile_planar_warp, planar_analysis_size, validate_planar_motion)
from planar_tracking import validate_planar_track
from planar_worker import measure


class PlanarScaleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg required for actual maximum-range pixel check")
    def test_last_sample_of_maximum_range_reaches_actual_warped_pixels(self):
        keys=[{"frame":frame,"matrix":IDENTITY.copy()} for frame in range(MAX_PLANAR_FRAMES)]
        keys[-1]["matrix"][2]=.5
        motion={"version":1,"mode":"stabilize","coordinates":COORDINATES,
                "canvas":{"width":32,"height":32},"outside":"identity","source":{},"keys":keys}
        chain=','.join(compile_planar_warp(motion,MAX_PLANAR_FRAMES-1,32,32))
        # Identical coefficient ranges collapse exactly, so a long stationary
        # take does not expand into thousands of redundant GEQ branches.
        self.assertLess(len(chain),15000)
        with tempfile.TemporaryDirectory(prefix="cinematicum-PLANAR-SCALE-TEST-") as temporary:
            script=Path(temporary)/"warp.ffscript";script.write_text(chain)
            result=subprocess.run([shutil.which("ffmpeg"),"-v","error","-threads","1","-filter_threads","1",
                "-f","lavfi","-i","color=c=red:s=32x32:r=1:d=1","-filter_script:v",str(script),
                "-frames:v","1","-pix_fmt","rgba","-f","rawvideo","pipe:1"],
                capture_output=True,check=True,timeout=20)
        self.assertEqual(len(result.stdout),32*32*4)
        self.assertEqual(result.stdout[(16*32+4)*4+3],0)
        self.assertEqual(result.stdout[(16*32+28)*4+3],255)

    def test_long_take_resolution_obeys_whole_window_budget(self):
        self.assertEqual(planar_analysis_size(1920,1080,240),(1280,720))
        short=planar_analysis_size(3840,2160,240)
        long=planar_analysis_size(3840,2160,MAX_PLANAR_FRAMES)
        self.assertLess(long[0],short[0])
        for width,height in ((3840,2160),(2160,3840),(32768,16),(16,32768),(16,16)):
            for count in (1,240,300,MAX_PLANAR_FRAMES):
                with self.subTest(width=width,height=height,count=count):
                    w,h=planar_analysis_size(width,height,count)
                    self.assertEqual((w%2,h%2),(0,0))
                    self.assertLessEqual(max(w,h),MAX_PLANAR_ANALYSIS_EDGE)
                    self.assertLessEqual(w*h*count,MAX_PLANAR_DECODE_BYTES)
                    self.assertGreaterEqual(min(w,h),16)
        for count in (0,MAX_PLANAR_FRAMES+1,True,2.5):
            with self.subTest(count=count),self.assertRaises(ValueError):
                planar_analysis_size(1920,1080,count)

    def test_worker_rejects_excessive_windows_before_opening_runtime(self):
        request={"frames":"does-not-exist.gray","width":1280,"height":1280,
                 "count":MAX_PLANAR_FRAMES,"model":"projective",
                 "quad":[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]}
        with patch("planar_worker.runtime") as runtime:
            with self.assertRaisesRegex(ValueError,"byte bound"):measure(request)
            runtime.assert_not_called()
            for changes in ({"width":MAX_PLANAR_ANALYSIS_EDGE+1},{"count":MAX_PLANAR_FRAMES+1},{"count":True}):
                with self.subTest(changes=changes),self.assertRaises(ValueError):
                    measure({**request,**changes})
            runtime.assert_not_called()

    def test_maximum_range_survives_document_and_motion_validation(self):
        quad=[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]
        source={"duration":MAX_PLANAR_FRAMES,"sha256":"1"*64}
        sample={"visible":True,"matrix":IDENTITY,"corners":quad,"confidence":1.,
                "features":100,"inliers":100,"inlier_ratio":1.,"coverage":.7,
                "error_pixels":0.,"reason":""}
        w,h=planar_analysis_size(3840,2160,MAX_PLANAR_FRAMES)
        track={"version":1,"kind":"planar-track","model":"projective","coordinates":COORDINATES,
               "source":source,"reference_frame":0,"reference_quad":quad,
               "analysis_width":w,"analysis_height":h,
               "samples":[{**copy.deepcopy(sample),"frame":frame} for frame in range(MAX_PLANAR_FRAMES)]}
        accepted=validate_planar_track(json.loads(json.dumps(track)),source)
        self.assertEqual(len(accepted["samples"]),MAX_PLANAR_FRAMES)
        motion={"version":1,"mode":"stabilize","coordinates":COORDINATES,
                "canvas":{"width":3840,"height":2160},"outside":"identity","source":{},
                "keys":[{"frame":s["frame"],"matrix":s["matrix"]} for s in accepted["samples"]]}
        self.assertEqual(len(validate_planar_motion(motion,0,MAX_PLANAR_FRAMES)["keys"]),MAX_PLANAR_FRAMES)
        with self.assertRaisesRegex(ValueError,"byte bound"):
            validate_planar_track({**track,"analysis_width":1280,"analysis_height":1280},source)
        excessive=copy.deepcopy(track);excessive["samples"].append({**sample,"frame":MAX_PLANAR_FRAMES})
        with self.assertRaises(ValueError):validate_planar_track(excessive,source)


if __name__=="__main__":unittest.main()
