"""Real HTTP/Store/archive boundary tests; never fake successful lens inference.

The queue test cancels its valid request behind an owned queue gate before any
calibration can run. The inert ENGINE TEST artifact inventory exercises saved
result/hash/portable-file contracts, not the scientific calibration validator.
Actual detector/fit behavior is tested in test_lens_calibration_smoke.py.
"""
from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
import zlib

import lens_calibration as calibration
import project_archive
import studio_tools
from server import Server,Store


def png(path,index=0):
    def chunk(name,data):
        return struct.pack(">I",len(data))+name+data+struct.pack(">I",zlib.crc32(name+data)&0xffffffff)
    rows=b"".join(b"\0"+bytes((32+index,90+y,140))*64 for y in range(64))
    data=b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",64,64,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(rows))+chunk(b"IEND",b"")
    path.write_bytes(data)
    return data


class LensCalibrationIntegration(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix="cinematicum-LENS-HTTP-ENGINE-TEST-")
        self.root=Path(self.temporary.name)
        self.home=self.root/"home";self.home.mkdir()
        self.home_patch=patch.object(Path,"home",return_value=self.home);self.home_patch.start()
        self.store=Store(self.root/"workspace")
        self.project=self.store.new_project({"name":"ENGINE TEST calibration boundaries","width":160,"height":90,"fps":24})
        self.ident=self.project["id"];self.base="/api/projects/"+self.ident
        self.server=Server(0,self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={"poll_interval":.01},daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.store.shutdown();self.home_patch.stop();self.temporary.cleanup()

    def request(self,method,path,body=None,token=True):
        headers={"X-Cinematicum-Token":self.store.token} if token else {}
        if isinstance(body,dict):body=json.dumps(body).encode();headers["Content-Type"]="application/json"
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        connection.request(method,path,body,headers)
        response=connection.getresponse();content=response.read();status=response.status
        if response.getheader("Content-Type","").startswith("application/json"):content=json.loads(content)
        connection.close()
        return status,content

    def inventory(self):
        """Inert bytes for custody/transport; no worker output is represented."""
        output_id="a"*32;directory=self.store.project_dir(self.ident)/"lens-calibration"/"outputs"/output_id
        directory.mkdir(parents=True)
        (directory/"calibration.json").write_text('{"ENGINE_TEST_ONLY":"artifact custody, not measured calibration"}\n')
        (directory/"observations.json").write_text('{"ENGINE_TEST_ONLY":true}\n')
        (directory/"opencv.yml").write_text('%YAML:1.0\nENGINE_TEST_ONLY: 1\n')
        png(directory/"preview.png")
        with zipfile.ZipFile(directory/"corners.zip","w") as archive:archive.writestr("ENGINE_TEST_ONLY.txt","No detector inference was performed in this transport fixture.\n")
        entries=[]
        for path in sorted(directory.iterdir()):
            content=path.read_bytes();entries.append({"filename":path.name,"sha256":hashlib.sha256(content).hexdigest(),"size":len(content)})
        receipt={"type":"cinematicum-lens-calibration","version":1,"ENGINE_TEST_ONLY":True,"artifacts":entries}
        (directory/"provenance.json").write_text(json.dumps(receipt)+"\n")
        return output_id,directory,receipt

    def test_real_get_capability_and_static_routes(self):
        before=set(self.home.rglob("*"))
        # Exercise actual missing-runtime behavior; never mock a healthy doctor.
        with patch.object(calibration,"_command",side_effect=RuntimeError("ENGINE TEST isolated runtime unavailable")):
            status,capability=self.request("GET","/api/lens-calibration-capabilities")
        self.assertEqual(status,200);self.assertFalse(capability["available"])
        self.assertIn("ENGINE TEST",capability["reason"])
        self.assertEqual(before,set(self.home.rglob("*")))
        status,content=self.request("GET","/lens-calibration-ui.js")
        self.assertEqual(status,200)
        self.assertEqual(content,(Path(__file__).parent/"web/lens-calibration-ui.js").read_bytes())
        status,index=self.request("GET","/index.html")
        self.assertEqual(status,200);self.assertIn(b'data-authoring-tool="lens-calibration"',index)
        self.assertIn(b'<script src="/lens-calibration-ui.js" defer></script>',index)
        _,module=studio_tools.implementation("lens-calibration")
        self.assertIs(module,calibration)
        self.assertIsNone(studio_tools.TOOLS["lens-calibration"]["field"])

    def test_real_authenticated_post_recipe_validation_and_owned_queued_cancellation(self):
        self.assertEqual(self.request("POST",self.base+"/lens-calibration",{"recipe":{}},token=False)[0],403)
        settings={**calibration.default_settings(),"asset_ids":[],"same_optics_confirmed":True}
        for extra in ("python","runtime","output_dir","command"):
            body={"recipe":{"operation":"calibrate_checkerboard","settings":settings},extra:"/not/browser/authority"}
            self.assertEqual(self.request("POST",self.base+"/lens-calibration",body)[0],400)
        self.assertFalse(self.store.jobs)
        for index in range(12):
            path=self.root/("ENGINE_TEST_%02d.png"%index);png(path,index)
            settings["asset_ids"].append(self.store.admit(self.ident,path,path.name)["id"])
        started=threading.Event();release=threading.Event()
        def wait(job_id,progress,event):
            started.set()
            while not release.wait(.01):
                if event.is_set():raise InterruptedError("ENGINE TEST gate cancelled")
            return {"ENGINE_TEST_ONLY":True}
        self.store.submit(self.ident,"ENGINE-TEST-owned-queue-gate",wait)
        self.assertTrue(started.wait(2))
        try:
            with patch.object(calibration,"run",side_effect=AssertionError("Cancelled request must never start inference")):
                status,job=self.request("POST",self.base+"/lens-calibration",{"recipe":{"operation":"calibrate_checkerboard","settings":settings}})
                self.assertEqual(status,202);self.assertEqual(job["kind"],"lens-calibration")
                self.assertEqual(job["project_id"],self.ident);self.assertEqual(job["state"],"queued")
                snapshot=json.loads((self.store.root/"jobs"/(job["id"]+".snapshot")).read_text())
                self.assertEqual(snapshot["recipe"]["settings"]["asset_ids"],settings["asset_ids"])
                self.assertNotIn("python",snapshot["recipe"])
                status,cancelled=self.request("POST","/api/jobs/"+job["id"]+"/cancel",{})
                self.assertEqual(status,200);self.assertEqual(cancelled["state"],"cancelled")
                self.assertFalse((self.store.project_dir(self.ident)/"lens-calibration"/"outputs"/job["id"]).exists())
        finally:release.set()

    def test_real_artifact_history_hash_checks_and_missing_output_404(self):
        missing=self.base+"/lens-calibration/outputs/"+"b"*32+"/calibration.json"
        self.assertEqual(self.request("GET",missing)[0],404)
        output_id,directory,_=self.inventory()
        result=studio_tools.publish_result(self.store,self.ident,"lens-calibration",output_id,{"ENGINE_TEST_ONLY":True})
        status,history=self.request("GET",self.base+"/studio-results")
        self.assertEqual(status,200);self.assertEqual(history["results"][0]["tool"],"lens-calibration")
        self.assertEqual(set(result["artifact_urls"]),calibration.ARTIFACT_NAMES)
        url=result["artifact_urls"]["calibration.json"]
        status,content=self.request("GET",url)
        self.assertEqual(status,200);self.assertIn("ENGINE_TEST_ONLY",content)
        (directory/"calibration.json").write_text("changed bytes\n")
        self.assertEqual(self.request("GET",url)[0],400)
        self.assertEqual(self.request("GET",self.base+"/lens-calibration/outputs/"+output_id+"/private.txt")[0],400)

    def test_actual_archive_roundtrip_preserves_registered_outputs_without_job_database(self):
        output_id,directory,_=self.inventory()
        for name in calibration.ARTIFACT_NAMES:
            self.assertTrue(project_archive._allowed("lens-calibration/outputs/"+output_id+"/"+name))
        for relative in ("lens-calibration/outputs/not-an-id/calibration.json","lens-calibration/outputs/"+output_id+"/private.txt","lens-calibration/sources/unowned.png"):
            self.assertFalse(project_archive._allowed(relative))
        archive=self.root/"ENGINE_TEST.cinematicum.zip"
        project_archive.export_archive(self.store.get(self.ident),self.store.project_dir(self.ident),archive)
        restored=project_archive.import_archive(archive,self.store.root/"projects")
        self.assertNotEqual(restored["id"],self.ident)
        records=studio_tools.list_results(self.store,restored["id"])
        self.assertEqual(len(records),1);self.assertEqual(records[0]["tool"],"lens-calibration")
        for name in calibration.ARTIFACT_NAMES:
            path=studio_tools.artifact(self.store,restored["id"],"lens-calibration",output_id,name)
            self.assertEqual(path.read_bytes(),(directory/name).read_bytes())
        status,content=self.request("GET",records[0]["artifact_urls"]["calibration.json"])
        self.assertEqual(status,200);self.assertIn("ENGINE_TEST_ONLY",content)


if __name__=="__main__":unittest.main()
