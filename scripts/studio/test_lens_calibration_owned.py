"""Actual owned calibration publication on generated ENGINE TEST photographs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent


def owned_case():
    # This subprocess is the selected isolated runtime. The application's test
    # discovery process never imports OpenCV/NumPy.
    sys.path.insert(0,str(HERE))
    import lens_calibration as backend
    import lens_calibration_worker as worker
    from test_lens_calibration_worker import _settings,_rotation,_project
    cv,np=worker.runtime();config=_settings(12);width,height=960,720;side=40
    k=np.array([[680.,0,480.],[0,690.,360.],[0,0,1.]])
    target=np.full((9*side,11*side),255,np.uint8)
    for row in range(7):
        for column in range(9):
            if (row+column)%2==0:target[(row+1)*side:(row+2)*side,(column+1)*side:(column+2)*side]=0
    source=np.array([[0,0],[target.shape[1]-1,0],[target.shape[1]-1,target.shape[0]-1],[0,target.shape[0]-1]],np.float32)
    plane=np.column_stack(((source-(2*side-.5))*25./side,np.zeros(4)));center=np.array([87.5,62.5,0.])
    with tempfile.TemporaryDirectory(prefix="cinematicum-OWNED-LENS-ENGINE-TEST-") as temporary:
        root=Path(temporary);media=root/"media";media.mkdir();assets=[];originals={}
        for i,ident in enumerate(config["asset_ids"]):
            x=(.30,.50,.70)[i%3];y=(.29,.43,.57,.71)[i//3];z=395.+18*(i%2)
            rotation=_rotation(np,(-.27,.22,.31,-.18)[i%4],(-.29,.27,.12)[i%3],.045*(i%3-1))
            translation=np.array([(x*width-480.)*z/680.,(y*height-360.)*z/690.,z])-rotation@center
            destination=_project(np,plane,rotation,translation,k,np.zeros(5)).astype(np.float32)
            image=cv.warpPerspective(target,cv.getPerspectiveTransform(source,destination),(width,height),flags=cv.INTER_LINEAR,borderMode=cv.BORDER_CONSTANT,borderValue=180)
            path=media/(ident+".png");assert cv.imwrite(str(path),image);data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
            assets.append({"id":ident,"name":"ENGINE TEST "+ident,"kind":"image","path":"media/"+path.name,
                "width":width,"height":height,"size":len(data),"sha256":digest});originals[path]=digest
        project={"id":"ENGINE_TEST","assets":assets};output=root/"lens-calibration"/"outputs"/("a"*32)
        result=backend.run(project,root,{"operation":"calibrate_checkerboard","settings":config},output,python=sys.executable)
        assert output.is_dir() and result["output_id"]=="a"*32 and result["lens_profile"]
        assert result["quality"]["holdout_rms_pixels"]<.3
        receipt=json.loads((output/"provenance.json").read_text());assert receipt["engine"]["opencv"]==cv.__version__
        expected={item["filename"] for item in receipt["artifacts"]}|{"provenance.json"}
        assert {path.name for path in output.iterdir()}==expected
        for item in receipt["artifacts"]:
            data=(output/item["filename"]).read_bytes();assert hashlib.sha256(data).hexdigest()==item["sha256"] and len(data)==item["size"]
        assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in originals.items())
        assert not any(path.name.startswith(".calibration-") for path in output.parent.iterdir())
        before=(output/"provenance.json").read_bytes()
        try:backend.run(project,root,{"operation":"calibrate_checkerboard","settings":config},output,python=sys.executable)
        except ValueError as exc:assert "overwritten" in str(exc)
        else:raise AssertionError("Existing immutable calibration output was overwritten")
        assert before==(output/"provenance.json").read_bytes()
        print(json.dumps({"case":"owned_calibration","actual_SB_views":12,"holdout_rms":result["quality"]["holdout_rms_pixels"],
            "artifacts_verified":len(expected),"originals_verified":len(originals),"scope":"generated ENGINE TEST, not production lens acceptance"}))


class OwnedCalibrationEngineTest(unittest.TestCase):
    def test_actual_owned_worker_publication_preserves_sources_and_immutable_outputs(self):
        python=os.environ.get("CINEMATICUM_TRACKING_PYTHON",sys.executable)
        try:
            probe=subprocess.run([python,"-I","-B",str(HERE/"lens_calibration_worker.py"),"--doctor"],capture_output=True,text=True,timeout=15)
            state=json.loads(probe.stdout) if probe.returncode==0 else {}
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:raise unittest.SkipTest("Actual isolated OpenCV runtime unavailable: "+str(exc))
        if not state.get("runtime_operations_verified"):raise unittest.SkipTest("Actual isolated OpenCV doctor failed: "+probe.stderr[:300])
        result=subprocess.run([python,"-I","-B",str(Path(__file__).resolve()),"--owned-case"],capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        if result.stdout:print(result.stdout.strip())


if __name__=="__main__":
    if sys.argv[1:]==["--owned-case"]:owned_case()
    else:unittest.main()
