"""Real Store/HTTP/file-boundary tests; no successful model inference is mocked.

Generated PNG/MP4 files are explicitly ENGINE TEST fixtures. The actual model
doctor is run only with missing/incompatible runtime fixtures and must fail
closed. CameraCtrl/DiffusionLight output acceptance is not established here.
"""
import copy
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zlib

import model_inference as models
from server import Store, Server


def photograph(path):
    width,height=64,48
    def chunk(name,data):
        return struct.pack(">I",len(data))+name+data+struct.pack(">I",zlib.crc32(name+data)&0xffffffff)
    rows=b"".join(b"\0"+bytes((32+y,90,140))*width for y in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(rows))+chunk(b"IEND",b""))


def hdr_archive_fixture(path):
    """Independent valid scanline float EXR; no model generated these pixels."""
    width,height=16,8
    def attribute(name,kind,data):
        return name.encode()+b"\0"+kind.encode()+b"\0"+struct.pack("<I",len(data))+data
    channels=b"".join(name.encode()+b"\0"+struct.pack("<iB3xii",2,0,1,1) for name in ("B","G","R"))+b"\0"
    window=struct.pack("<4i",0,0,width-1,height-1)
    header=b"\x76\x2f\x31\x01"+struct.pack("<I",2)
    for name,kind,data in (("channels","chlist",channels),("compression","compression",b"\0"),("dataWindow","box2i",window),("displayWindow","box2i",window),("lineOrder","lineOrder",b"\0"),("pixelAspectRatio","float",struct.pack("<f",1.)),("screenWindowCenter","v2f",struct.pack("<2f",0.,0.)),("screenWindowWidth","float",struct.pack("<f",1.))):
        header+=attribute(name,kind,data)
    header+=b"\0"
    chunks=[struct.pack("<iI",y,width*3*4)+b"".join(struct.pack("<f",.1+channel+x/width+y/height) for channel in range(3) for x in range(width)) for y in range(height)]
    offset=len(header)+8*height;offsets=[]
    for chunk in chunks:offsets.append(offset);offset+=len(chunk)
    path.write_bytes(header+b"".join(struct.pack("<Q",value) for value in offsets)+b"".join(chunks))


class ModelInferenceIntegration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="cinematicum-MODEL-INTEGRATION-ENGINE-TEST-")
        self.root=Path(self.temp.name)
        self.home=self.root/"home"; self.home.mkdir()
        self.home_patch=patch.object(Path,"home",return_value=self.home)
        self.home_patch.start()
        self.store=Store(self.root/"workspace")
        self.project=self.store.new_project({"name":"ENGINE TEST model boundaries","width":160,"height":90,"fps":24})
        self.project_id=self.project["id"]
        self.base=f"/api/projects/{self.project_id}"
        self.server=Server(0,self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={"poll_interval":.02},daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.store.shutdown()
        self.home_patch.stop();self.temp.cleanup()

    def request(self,method,path,body=None,token=True):
        headers={"X-Cinematicum-Token":self.store.token} if token else {}
        if isinstance(body,dict):
            body=json.dumps(body).encode();headers["Content-Type"]="application/json"
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=10)
        connection.request(method,path,body,headers)
        response=connection.getresponse();data=response.read();status=response.status
        if response.getheader("Content-Type","").startswith("application/json"):
            data=json.loads(data)
        connection.close()
        return status,data

    def profile(self,model="camera_ctrl"):
        directory=models._profile_root()/model;directory.mkdir(parents=True,exist_ok=True)
        manifest=self.root/(model+"-missing-models.json");manifest.write_text("{}")
        runtime={"python":sys.executable,"upstream_root":str(self.root/"missing-upstream"),"model_manifest":str(manifest),
                 "model_manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),"device":"cuda:0" if model=="camera_ctrl" else "cpu"}
        if model=="camera_ctrl":
            runtime.update(ffmpeg=shutil.which("ffmpeg"),ffprobe=shutil.which("ffprobe"))
        path=directory/"runtime.json";path.write_text(json.dumps(runtime))
        return path,runtime

    def settled(self,job_id):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            job=self.store.job(job_id)
            if job["state"] not in {"queued","running"}:return job
            time.sleep(.01)
        self.fail("The actual owned boundary-test job did not settle")

    def gate(self):
        started=threading.Event();release=threading.Event()
        def wait(job_id,progress,event):
            started.set()
            while not release.wait(.01):
                if event.is_set():raise RuntimeError("ENGINE TEST gate cancelled")
            return {"engine_test_gate":True}
        job=self.store.submit(self.project_id,"ENGINE-TEST-owned-queue-gate",wait)
        self.assertTrue(started.wait(2))
        self.addCleanup(release.set)
        return release,job

    def test_status_is_read_only_cheap_and_explicitly_unverified(self):
        before=set(self.home.rglob("*"))
        with patch.object(models.importlib,"import_module",side_effect=AssertionError("Status imported a backend")):
            code,result=self.request("GET","/api/model-inference/status")
        self.assertEqual(code,200)
        self.assertEqual(set(self.home.rglob("*")),before)
        self.assertFalse(result["automatic_installation"])
        self.assertEqual(len(result["models"]),2)
        self.assertTrue(all(not item["configured"] and not item["runtime_verified"] and not item["inference_accepted"] for item in result["models"]))
        self.assertEqual(self.request("POST",self.base+"/model-inference-doctor",{"model":"camera_ctrl"},token=False)[0],403)

    def test_browser_cannot_select_runtime_or_output_paths(self):
        self.profile()
        for extra in ("python","runtime","upstream_root","model_manifest","output_dir"):
            code,_=self.request("POST",self.base+"/model-inference-doctor",{"model":"camera_ctrl",extra:"/not/browser/authority"})
            self.assertEqual(code,400)
        self.assertFalse(self.store.jobs)

    def test_actual_unavailable_doctor_is_owned_job_and_saved_artifact(self):
        self.profile()
        code,submitted=self.request("POST",self.base+"/model-inference-doctor",{"model":"camera_ctrl"})
        self.assertEqual(code,202)
        self.assertEqual(submitted["kind"],"model-camera_ctrl-doctor")
        job=self.settled(submitted["id"])
        self.assertEqual(job["state"],"completed")
        result=job["result"]
        self.assertFalse(result["report"]["available"])
        self.assertFalse(result["inference_executed"])
        self.assertFalse(self.store.get(self.project_id)["assets"])
        code,doctor=self.request("GET",result["artifact_urls"]["doctor.json"])
        self.assertEqual(code,200)
        self.assertFalse(doctor["available"])
        code,history=self.request("GET",self.base+"/model-inference-results")
        self.assertEqual(code,200)
        self.assertEqual(history["results"][0]["output_id"],submitted["id"])
        self.assertFalse(history["results"][0]["inference_executed"])
        snapshot=(self.store.root/"jobs"/(submitted["id"]+".snapshot")).read_text()
        self.assertNotIn('"python"',snapshot)
        self.assertNotIn("missing-upstream",snapshot)

    def test_saved_artifact_tampering_and_symlinks_are_rejected(self):
        self.profile()
        job=self.settled(models.submit(self.store,self.project_id,"doctor",{"model":"camera_ctrl"})["id"])
        output=job["result"]["output_id"]
        path=models.artifact(self.store,self.project_id,output,"doctor.json")
        original=path.read_bytes();path.write_bytes(original+b" ")
        with self.assertRaises(ValueError):models.artifact(self.store,self.project_id,output,"doctor.json")
        path.unlink();elsewhere=self.root/"outside.json";elsewhere.write_bytes(original);path.symlink_to(elsewhere)
        with self.assertRaises(ValueError):models.artifact(self.store,self.project_id,output,"doctor.json")
        with self.assertRaises(ValueError):models.artifact(self.store,self.project_id,output,"../runtime.json")

    def test_queued_profile_change_fails_before_worker_launch(self):
        profile,runtime=self.profile()
        release,_=self.gate()
        queued=models.submit(self.store,self.project_id,"doctor",{"model":"camera_ctrl"})
        runtime["upstream_root"]=str(self.root/"changed-upstream");profile.write_text(json.dumps(runtime))
        release.set();job=self.settled(queued["id"])
        self.assertEqual(job["state"],"failed")
        self.assertIn("profile changed",job["error"])
        self.assertFalse((self.store.project_dir(self.project_id)/"model-inference"/"runs"/queued["id"]).exists())

    def test_cancellation_of_queued_doctor_never_starts_worker(self):
        self.profile()
        release,_=self.gate()
        queued=models.submit(self.store,self.project_id,"doctor",{"model":"camera_ctrl"})
        self.store.cancel(queued["id"]);release.set()
        job=self.settled(queued["id"])
        self.assertEqual(job["state"],"cancelled")
        self.assertFalse((self.store.project_dir(self.project_id)/"model-inference"/"runs"/queued["id"]).exists())

    def test_changed_owned_photo_is_rejected_before_actual_worker(self):
        self.profile("diffusionlight")
        photo=self.root/"ENGINE_TEST_source.png";photograph(photo)
        asset=self.store.admit(self.project_id,photo,"ENGINE TEST source.png")
        release,_=self.gate()
        queued=models.submit(self.store,self.project_id,"infer",{"model":"diffusionlight","source_id":asset["id"],"options":{}})
        source=self.store.project_dir(self.project_id)/asset["path"]
        source.write_bytes(source.read_bytes()+b"ENGINE TEST tampered")
        release.set();job=self.settled(queued["id"])
        self.assertEqual(job["state"],"failed")
        self.assertIn("admitted identity",job["error"])
        self.assertFalse((self.store.project_dir(self.project_id)/"model-inference"/"runs"/queued["id"]/"worker").exists())

    def test_source_photo_cannot_come_from_another_project(self):
        self.profile("diffusionlight")
        other=self.store.new_project({"name":"ENGINE TEST other project","width":160,"height":90})
        photo=self.root/"ENGINE_TEST_other.png";photograph(photo)
        asset=self.store.admit(other["id"],photo,"ENGINE TEST other.png")
        with self.assertRaises(ValueError):models.submit(self.store,self.project_id,"infer",{"model":"diffusionlight","source_id":asset["id"],"options":{}})

    def test_real_engine_test_movie_decoder_checks_sixteen_frames(self):
        movie=self.root/"ENGINE_TEST_not_model_output.mp4"
        subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-y","-f","lavfi","-i","testsrc2=s=384x256:r=8:d=2", "-threads","1","-c:v","libx264","-pix_fmt","yuv420p",str(movie)],check=True)
        probe=models._movie({"ffprobe":shutil.which("ffprobe")},movie,{"fps":8},threading.Event())
        self.assertEqual(int(probe["streams"][0]["nb_read_frames"]),16)
        with self.assertRaises(ValueError):models._movie({"ffprobe":shutil.which("ffprobe")},movie,{"fps":24},threading.Event())
        self.assertFalse(self.store.get(self.project_id)["assets"])

    def test_actual_media_admission_keeps_different_hdr_derivative_provenance(self):
        assets=[]
        for identity in ("1"*64,"2"*64):
            photo=self.root/("ENGINE_TEST_"+identity[:1]+".png");photograph(photo)
            assets.append(self.store.admit(self.project_id,photo,"ENGINE TEST SDR derivative.png",{"type":"cinematicum-diffusionlight-display","linear_environment_sha256":identity}))
        self.assertEqual(assets[0]["sha256"],assets[1]["sha256"])
        self.assertNotEqual(assets[0]["id"],assets[1]["id"])

    def test_portable_archive_keeps_actual_hdr_fixture_and_original_receipt_identity(self):
        import project_archive
        output_id="a"*32
        output=self.store.project_dir(self.project_id)/"model-inference"/"outputs"/output_id
        output.mkdir(parents=True)
        hdr=output/"environment.exr";hdr_archive_fixture(hdr)
        receipt={"schema":"cinematicum-model-inference","version":1,"model":"diffusionlight","operation":"doctor",
            "project_id":self.project_id,"output_id":output_id,"profile_sha256":"0"*64,"inputs":{},"inference_executed":False,
            "production_accepted":False,"worker_report":{"available":False,"error":"ENGINE TEST independent archive fixture; no inference"},
            "artifacts":[{"filename":"environment.exr","sha256":hashlib.sha256(hdr.read_bytes()).hexdigest(),"bytes":hdr.stat().st_size}]}
        models._write(output/"provenance.json",receipt)
        archive=self.root/"ENGINE_TEST_portable.zip"
        project_archive.export_archive(self.store.get(self.project_id),self.store.project_dir(self.project_id),archive)
        restored=project_archive.import_archive(archive,self.store.root/"projects")
        self.assertNotEqual(restored["id"],self.project_id)
        copied=models.artifact(self.store,restored["id"],output_id,"environment.exr")
        self.assertEqual(copied.read_bytes(),hdr.read_bytes())
        history=models.list_results(self.store,restored["id"])
        self.assertIn("/projects/"+restored["id"]+"/",history[0]["artifact_urls"]["environment.exr"])
        self.assertFalse(history[0]["inference_executed"])
        self.assertEqual(json.loads(copied.with_name("provenance.json").read_text())["project_id"],self.project_id)

    def test_failed_media_admission_retains_already_published_files_without_inference_claim(self):
        # Private publication-contract unit test. A real PNG fixture is inert
        # artifact bytes here; no model output or successful inference is faked.
        output_id="b"*32
        directory=self.store.project_dir(self.project_id)
        run=directory/"model-inference"/"runs"/output_id;run.mkdir(parents=True)
        fixture=run/"ENGINE_TEST_inert_file.png";photograph(fixture)
        with patch.object(self.store,"admit",side_effect=ValueError("ENGINE TEST simulated full Media bin")):
            result=models._publish(self.store,self.project_id,"camera_ctrl","infer",output_id,run,{"output.mp4":fixture},
                {"inference_executed":False,"engine_test_fixture":True},"0"*64,{},threading.Event())
        self.assertEqual(result["media_admission"],"failed_after_publication")
        self.assertFalse(result["inference_executed"])
        self.assertEqual(models.artifact(self.store,self.project_id,output_id,"output.mp4").read_bytes(),fixture.read_bytes())


if __name__=="__main__":unittest.main()
