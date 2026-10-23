"""Data-integrity and independent physical-projection contracts, without OpenCV."""
from __future__ import annotations

import copy
import math
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

import lens_calibration as calibration


def fixture():
    """Prescribed physical geometry for validator tests, not measured inference."""
    settings={**calibration.default_settings(),"asset_ids":["photo_"+str(i) for i in range(12)],"same_optics_confirmed":True}
    views=[];observed=[];square=.025
    for index,ident in enumerate(settings["asset_ids"]):
        ax=(index%4-1.5)*.16;ay=(index//4-1)*.22
        ca,sa,cb,sb=math.cos(ax),math.sin(ax),math.cos(ay),math.sin(ay)
        rotation=[cb,0,sb,sa*sb,ca,-sa*cb,-ca*sb,sa,ca*cb]
        translation=[-.09+.01*(index%4),-.055+.01*(index//4),.65+.025*(index%3)]
        corners=[]
        for row in range(settings["rows"]):
            for column in range(settings["columns"]):
                world=[column*square,row*square,0]
                xyz=[sum(rotation[r*3+c]*world[c] for c in range(3))+translation[r] for r in range(3)]
                corners.append([600*xyz[0]/xyz[2]+320,580*xyz[1]/xyz[2]+240])
        views.append({"asset_id":ident,"rotation":rotation,"translation":translation,"rms_pixels":0.,"training":index>=2})
        observed.append({"asset_id":ident,"corners":corners})
    result={"version":1,"kind":"checkerboard-lens-calibration","image_size":{"width":640,"height":480},
        "camera_matrix":[[600.,0.,320.],[0.,580.,240.],[0.,0.,1.]],"distortion":[0.]*5,
        "parameter_order":["fx","fy","cx","cy","k1","k2","p1","p2"],
        "covariance":[[1e-4 if i==j else 0 for j in range(8)] for i in range(8)],
        "views":views,"quality":{"observability":{"rank":8,"condition":10.}},"rolling_shutter":{"estimated":False},
        "settings":settings,"pixel_convention":"zero-based-integer-pixel-centers"}
    observations={"version":1,"kind":"checkerboard-observations","views":observed,"rejected":[],
        "pixel_convention":"zero-based-integer-pixel-centers","board":{"columns":8,"rows":6,"square_size_mm":25.}}
    return settings,result,observations


class LensCalibrationContracts(unittest.TestCase):
    def test_application_import_does_not_load_optional_numeric_runtimes(self):
        script="import sys;sys.path.insert(0,sys.argv[1]);import lens_calibration;print([n for n in ('cv2','numpy') if n in sys.modules])"
        result=subprocess.run([sys.executable,"-I","-B","-c",script,str(Path(__file__).parent)],capture_output=True,text=True,check=True,timeout=5)
        self.assertEqual(result.stdout.strip(),"[]")

    def test_recipe_requires_fixed_physical_geometry_and_admitted_uniform_views(self):
        settings,_,_=fixture();project={"assets":[{"id":ident,"kind":"image","width":640,"height":480,"path":"media/"+ident+".png"} for ident in settings["asset_ids"]]}
        recipe={"operation":"calibrate_checkerboard","settings":settings}
        self.assertEqual(calibration.validate_recipe(recipe,project),recipe)
        for change in ({"same_optics_confirmed":False},{"square_size_mm":0},{"rows":True},{"radial_terms":4},{"command":"external"}):
            with self.subTest(change=change),self.assertRaises(ValueError):calibration.validate_recipe({**recipe,"settings":{**settings,**change}},project)
        bad=copy.deepcopy(project);bad["assets"][0]["width"]=641
        with self.assertRaises(ValueError):calibration.validate_recipe(recipe,bad)

    def test_independent_projection_verification_rejects_changed_pixels_or_camera(self):
        settings,result,observed=fixture()
        self.assertIs(calibration.validate_measurement(result,observed,settings,640,480),result)
        changed=copy.deepcopy(observed);changed["views"][0]["corners"][0][0]+=1
        with self.assertRaisesRegex(ValueError,"RMS"):calibration.validate_measurement(result,changed,settings,640,480)
        changed=copy.deepcopy(result);changed["camera_matrix"][0][0]+=1
        with self.assertRaisesRegex(ValueError,"RMS"):calibration.validate_measurement(changed,observed,settings,640,480)

    def test_covariance_is_full_ordered_positive_definite_and_observability_declared(self):
        settings,result,observed=fixture()
        for mutation in (lambda v:v["covariance"][0].__setitem__(0,-1),
                lambda v:v["covariance"][0].__setitem__(1,1),
                lambda v:v["parameter_order"].reverse(),
                lambda v:v["quality"]["observability"].update(rank=7),
                lambda v:v["quality"]["observability"].update(condition=1e12)):
            bad=copy.deepcopy(result);mutation(bad)
            with self.assertRaises(ValueError):calibration.validate_measurement(bad,observed,settings,640,480)

    def test_views_must_preserve_source_holdout_and_omission_evidence(self):
        settings,result,observed=fixture()
        for mutation in (lambda v:v["views"][0].update(asset_id="not-admitted"),
                lambda v:[row.update(training=True) for row in v["views"]],
                lambda v:v["views"][0]["rotation"].__setitem__(0,0),
                lambda v:v["rolling_shutter"].update(estimated=True)):
            bad=copy.deepcopy(result);mutation(bad)
            with self.assertRaises(ValueError):calibration.validate_measurement(bad,observed,settings,640,480)
        with self.assertRaises(ValueError):calibration.validate_measurement(result,{**observed,"rejected":[{"asset_id":"unknown","reason":"not detected"}]},settings,640,480)

    def test_cancelled_or_expired_worker_does_not_start_any_process(self):
        event=threading.Event();event.set()
        with patch("lens_calibration.subprocess.Popen") as launch:
            with self.assertRaises(InterruptedError):calibration._worker(["must-not-start"],{},".",event,time.monotonic()+1)
            with self.assertRaises(TimeoutError):calibration._worker(["must-not-start"],{},".",None,time.monotonic()-1)
            launch.assert_not_called()


if __name__=="__main__":unittest.main()
