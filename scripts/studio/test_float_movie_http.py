"""Actual FLOAT32 ENGINE TEST media through owned HTTP jobs and downloads."""
import copy
import hashlib
import http.client
import io
import json
import threading
import time
import unittest
import zipfile

from server import Server, Store
from float_movie import DEFAULTS, verify_master_package
import test_float_movie as fixtures


@unittest.skipUnless(fixtures.FLOAT_RUNTIME, "Use the isolated NumPy/OCIO/OpenEXR Imaging interpreter")
class FloatMovieHTTPTests(unittest.TestCase):
    def setUp(self):
        self.media=fixtures.FloatMovieTests();self.media.setUp();self.root=self.media.root
        self.workspace=self.root/"workspace";self.store=Store(self.workspace)
        self.project=self.store.new_project({"name":"ENGINE TEST float HTTP", "fps":4,"width":32,"height":24})
        self.base="/api/projects/"+self.project["id"];self.releases=[];self.start_server()
        source=self.media.exr("source",(-.25,2,4),.375)
        data=(self.root/source["path"]).read_bytes()
        status,_,asset=self.request("POST",self.base+"/import?name=ENGINE_TEST_float.exr",data,{"Content-Type":"application/octet-stream"})
        self.assertEqual(status,201,asset);self.asset=asset
        self.project=self.store.get(self.project["id"])
        self.project["settings"]={"image_precision":"float32","transparent_background":True,"float_color":copy.deepcopy(DEFAULTS)}
        self.project["clips"]=[{"id":"ENGINE_TEST_float_clip","asset_id":asset["id"],"track":0,"in":0,"start":0,"duration":4,"float_input_space":"ACEScg"}]

    def start_server(self):
        self.server=Server(0,self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={"poll_interval":.02},daemon=True);self.thread.start()

    def stop_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.store.shutdown()

    def tearDown(self):
        for event in self.releases:event.set()
        self.stop_server();self.media.tearDown()

    def request(self,method,path,body=None,headers=None,token=True):
        headers=dict(headers or {})
        if token:headers["X-Cinematicum-Token"]=self.store.token
        if isinstance(body,dict):body=json.dumps(body).encode();headers["Content-Type"]="application/json"
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=20)
        try:
            connection.request(method,path,body=body,headers=headers)
            response=connection.getresponse();data=response.read();received=dict(response.getheaders())
            if received.get("Content-Type","").startswith("application/json"):data=json.loads(data)
            return response.status,received,data
        finally:connection.close()

    def terminal(self,job,timeout=20):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            status,_,job=self.request("GET","/api/jobs/"+job["id"]);self.assertEqual(status,200,job)
            if job["state"] not in {"queued","running"}:return job
            time.sleep(.03)
        self.fail("Owned float job did not terminate: "+str(job))

    def save(self):
        status,_,saved=self.request("PUT",self.base,self.project);self.assertEqual(status,200,saved);self.project=saved;return saved

    def test_http_save_reopen_float_preview_master_download_and_archive_bindings(self):
        saved=self.save();directory=self.store.project_dir(saved["id"])
        status,_,capabilities=self.request("GET","/api/float-movie-capabilities")
        self.assertEqual(status,200);self.assertTrue(capabilities["available"])
        status,_,preview=self.request("POST",self.base+"/frame-preview",{"project":saved,"frame":2})
        self.assertEqual(status,202,preview);preview=self.terminal(preview);self.assertEqual(preview["state"],"completed",preview)
        self.assertEqual(preview["result"]["processing_bits"],32)
        status,_,png=self.request("GET",preview["result"]["url"]);self.assertEqual(status,200)
        self.assertEqual(hashlib.sha256(png).hexdigest(),preview["result"]["sha256"])
        self.assertEqual(png[:8],b"\x89PNG\r\n\x1a\n")
        forged=copy.deepcopy(saved);forged["assets"]=[]
        status,_,job=self.request("POST",self.base+"/render",{"profile":"master32","project":forged})
        self.assertEqual(status,202,job);job=self.terminal(job);self.assertEqual(job["state"],"completed",job)
        status,headers,data=self.request("GET",job["result"]["url"]+"?download=1")
        self.assertEqual(status,200);self.assertIn("attachment",headers.get("Content-Disposition",""))
        self.assertEqual(hashlib.sha256(data).hexdigest(),job["result"]["sha256"])
        self.assertEqual(len(data),job["result"]["size"])
        manifest=verify_master_package(io.BytesIO(data),saved)
        self.assertEqual(manifest["sources"][0]["sha256"],self.asset["sha256"])
        receipt=json.loads((directory/"exports"/(job["id"]+".json")).read_text())
        self.assertEqual(receipt["snapshot"],saved);self.assertEqual(receipt["issuance_effect"],"NONE")
        status,_,archive=self.request("POST",self.base+"/archive-export",{"project":saved})
        self.assertEqual(status,202,archive);archive=self.terminal(archive);self.assertEqual(archive["state"],"completed",archive)
        status,_,archive_bytes=self.request("GET",archive["result"]["url"]);self.assertEqual(status,200)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as package:
            self.assertEqual(package.read("exports/"+job["result"]["filename"]),data)
        self.stop_server();self.store=Store(self.workspace);self.start_server()
        status,_,reopened=self.request("GET",self.base);self.assertEqual(status,200);self.assertEqual(reopened,saved)
        status,_,durable=self.request("GET","/api/jobs/"+job["id"])
        self.assertEqual(status,200);self.assertEqual(durable["state"],"completed");self.assertEqual(durable["result"]["sha256"],job["result"]["sha256"])
        self.assertEqual(hashlib.sha256((directory/self.asset["path"]).read_bytes()).hexdigest(),self.asset["sha256"])

    def test_owned_queue_cancel_and_rejected_request_do_not_publish_any_master(self):
        saved=self.save();entered=threading.Event();release=threading.Event();self.releases.append(release)
        def owner(_ident,_progress,cancelled):
            entered.set()
            while not release.wait(.02):
                if cancelled.is_set():raise RuntimeError("ENGINE TEST owner cancelled")
            return {"engine_test_only":True}
        self.store.submit(saved["id"],"ENGINE_TEST_queue_owner",owner);self.assertTrue(entered.wait(2))
        status,_,error=self.request("POST",self.base+"/render",{"profile":"master32","project":saved},token=False)
        self.assertEqual(status,403,error)
        status,_,job=self.request("POST",self.base+"/render",{"profile":"master32","project":saved});self.assertEqual(status,202,job)
        status,_,cancelled=self.request("POST","/api/jobs/"+job["id"]+"/cancel",{})
        self.assertEqual(status,200);self.assertEqual(cancelled["state"],"cancelled",cancelled);release.set()
        directory=self.store.project_dir(saved["id"])
        self.assertFalse((directory/"exports"/(job["id"]+".zip")).exists())
        self.assertFalse((directory/"exports"/(job["id"]+".json")).exists())
        self.assertEqual(self.store.get(saved["id"]),saved)
        self.assertEqual(hashlib.sha256((directory/self.asset["path"]).read_bytes()).hexdigest(),self.asset["sha256"])


if __name__=="__main__":unittest.main()
