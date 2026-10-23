"""Dense adapter contracts; parser fixtures are ENGINE TEST data, not inference.

These tests do not certify an AliceVision runtime, GPU, captured image set or
production surface. A real configured engine acceptance is separately required.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile
import zlib

import alicevision as dense


def png(path,width=2,height=2):
    def chunk(kind,data):return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    raw=b"".join(b"\0"+bytes((31,127,223))*width for _ in range(height))
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+
        chunk(b"IDAT",zlib.compress(raw))+chunk(b"IEND",b""))


def surface(root):
    root=Path(root);root.mkdir(exist_ok=True)
    (root/"texturedMesh.obj").write_text("# ENGINE TEST parser fixture, not a measured surface\nmtllib texturedMesh.mtl\n"
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nusemtl Atlas\nf 1/1 2/2 3/3\n")
    (root/"texturedMesh.mtl").write_text("newmtl Atlas\nKd 1 1 1\nmap_Kd texture_1001.png\n")
    png(root/"texture_1001.png")


def settings():return {"version":1,"asset_ids":["a","b","c"],"downscale":4,"texture_side":2048,"require_all_images":True}


def graph(paths):
    value=json.loads(dense.GRAPH.read_text())
    value["graph"]["CameraInit_1"]["inputs"]["viewpoints"]=[{"path":path} for path in paths]
    value["graph"]["DepthMap_1"]["inputs"]["downscale"]=4
    value["graph"]["Texturing_1"]["inputs"].update(textureSide=2048,outputMeshFileType="obj",colorMapping={"colorMappingFileType":"png"})
    return value


def camera_record(root,inputs):
    path=Path(root)/"StructureFromMotion"/"ENGINE_TEST"/"cameras.sfm";path.parent.mkdir(parents=True)
    value={"views":[{"path":"/ENGINE_TEST/"+record["filename"],"poseId":str(i),"intrinsicId":"7"} for i,record in enumerate(inputs)],
        "poses":[{"poseId":str(i),"pose":{"transform":{"rotation":["1","0","0","0","1","0","0","0","1"],"center":[str(i),"0","0"]}}} for i in range(len(inputs))],
        "intrinsics":[{"intrinsicId":"7","width":"640","height":"480","focalLength":"35"}]}
    path.write_text(json.dumps(value));return path,value


class DenseRecipeTests(unittest.TestCase):
    def setUp(self):
        self.project={"assets":[{"id":name,"kind":"image","path":"media/"+name+".jpg","width":640,"height":480} for name in "abc"]}
        self.recipe={"operation":"meshroom_dense","settings":settings()}

    def test_typed_dense_inputs_have_distinct_engine_settings(self):
        self.assertEqual(dense.validate_recipe(self.recipe,self.project),self.recipe)
        for change in ({"asset_ids":["a","a","c"]},{"downscale":True},{"texture_side":8192},{"threads":4},{"require_all_images":"yes"}):
            with self.subTest(change=change),self.assertRaises(ValueError):dense.validate_recipe({**self.recipe,"settings":{**settings(),**change}},self.project)
        bad=copy.deepcopy(self.project);bad["assets"][0]["kind"]="video"
        with self.assertRaises(ValueError):dense.validate_recipe(self.recipe,bad)

    def test_pinned_graph_requires_dense_stage_links_and_exact_photographs(self):
        paths=["/owned/images/a.jpg","/owned/images/b.jpg","/owned/images/c.jpg"];value=graph(paths)
        self.assertEqual(len(dense.validate_graph(value,paths,settings())["graph"]),12)
        for mutation in (lambda v:v["graph"].pop("DepthMap_1"),
                lambda v:v["graph"]["Meshing_1"]["inputs"].update(depthMapsFolder="/external/fake"),
                lambda v:v["graph"]["Texturing_1"]["inputs"].update(colorMapping={"colorMappingFileType":"exr"}),
                lambda v:v["header"]["nodesVersions"].update(DepthMap="unknown"),
                lambda v:v["graph"]["CameraInit_1"]["inputs"]["viewpoints"].append({"path":"/external.jpg"})):
            bad=copy.deepcopy(value);mutation(bad)
            with self.assertRaises(ValueError):dense.validate_graph(bad,paths,settings())

    def test_absent_runtime_stays_unavailable_without_dense_acceptance(self):
        with patch.dict(os.environ,{},clear=True):result=dense.capabilities()
        self.assertFalse(result["available"]);self.assertFalse(result["actual_dense_acceptance"])
        self.assertIn("No Meshroom runtime",result["reason"])

    def test_cli_uses_saved_graph_dependencies_and_explicit_bounded_png_output(self):
        prepare,compute=dense._commands("/runtime/meshroom_batch","/runtime/meshroom_compute",
            "/owned/images","/owned/published","/owned/cache","/owned/configured.mg",settings())
        self.assertEqual(prepare[-2:],["--compute","no"])
        self.assertIn("DepthMap_1.downscale=4",prepare)
        self.assertIn("Texturing_1.colorMapping.colorMappingFileType=png",prepare)
        self.assertEqual(compute,["/runtime/meshroom_compute","/owned/configured.mg","--cache","/owned/cache","--toNode","Publish_1"])

    def test_cancelled_or_expired_job_never_starts_a_process(self):
        event=threading.Event();event.set()
        with patch("alicevision.subprocess.Popen") as launch:
            with self.assertRaises(InterruptedError):dense._execute(["must-not-start"],".","cancel",event,time.monotonic()+5)
            with self.assertRaises(TimeoutError):dense._execute(["must-not-start"],".","expired",None,time.monotonic()-1)
            launch.assert_not_called()

    def test_environment_keeps_upstream_temporary_files_inside_owned_scratch(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-DENSE-TMP-TEST-") as directory:
            env=dense._environment(directory);expected=str(Path(directory)/"engine-tmp")
            self.assertEqual([env[name] for name in ("TMPDIR","TMP","TEMP")],[expected]*3)
            self.assertTrue(Path(expected).is_dir())

    @unittest.skipUnless(hasattr(os,"killpg"),"Owned POSIX process groups required")
    def test_completed_leader_does_not_release_live_group_descendants(self):
        # A real short process-custody check; no photogrammetry engine runs.
        # The child retains the stdout pipe after its launcher has exited.
        command="import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); print('launcher exited',flush=True)"
        process=subprocess.Popen([sys.executable,"-c",command],stdout=subprocess.PIPE,start_new_session=True)
        try:
            process.wait(timeout=3)
            self.assertEqual(process.poll(),0)
            dense._stop(process)
            self.assertEqual(process.communicate(timeout=3)[0].strip(),b"launcher exited")
        finally:dense._stop(process)


class DenseOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix="cinematicum-DENSE-CONTRACT-TEST-")
        self.root=Path(self.temporary.name);self.output=self.root/"surface";surface(self.output)

    def tearDown(self):self.temporary.cleanup()

    def test_surface_has_real_uv_indices_owned_material_and_decodable_texture(self):
        stats,names=dense.validate_surface(self.output,2048)
        self.assertEqual((stats["vertices"],stats["faces"],stats["uv_coordinates"]),(3,1,3))
        self.assertEqual((stats["textures"][0]["width"],stats["textures"][0]["height"]),(2,2))
        archive=self.root/"mesh.zip"
        entries=dense._bundle(self.output,names,archive,None,time.monotonic()+5)
        with zipfile.ZipFile(archive) as result:self.assertEqual(set(result.namelist()),set(names))
        self.assertEqual({e["filename"] for e in entries},set(names))

    def test_assimp_three_component_uvs_preserve_the_actual_alicevision_format(self):
        mesh=self.output/"texturedMesh.obj"
        mesh.write_text(mesh.read_text().replace("vt 0 0","vt 0 0 0").replace("vt 1 0","vt 1 0 0").replace("vt 0 1","vt 0 1 0"))
        self.assertEqual(dense.validate_surface(self.output,2048)[0]["uv_coordinates"],3)
        mesh.write_text(mesh.read_text().replace("vt 0 0 0","vt 0 0 1"))
        with self.assertRaises(ValueError):dense.validate_surface(self.output,2048)

    def test_invalid_geometry_and_external_material_dependencies_are_rejected(self):
        mesh=self.output/"texturedMesh.obj";original=mesh.read_text()
        for replacement in (original.replace("3/3","999/3"),original.replace("f 1/1 2/2 3/3","f 1 2 3"),
                original.replace("v 0 0 0","v nan 0 0"),original.replace("texturedMesh.mtl","../other.mtl")):
            mesh.write_text(replacement)
            with self.assertRaises(ValueError):dense.validate_surface(self.output,2048)
        mesh.write_text(original)
        (self.output/"texturedMesh.mtl").write_text("newmtl Atlas\nmap_Kd ../external.png\n")
        with self.assertRaises(ValueError):dense.validate_surface(self.output,2048)

    def test_png_checks_pixels_crc_dimensions_and_inventory(self):
        texture=self.output/"texture_1001.png";original=texture.read_bytes()
        texture.write_bytes(original[:-5])
        with self.assertRaises(ValueError):dense.validate_surface(self.output,2048)
        texture.write_bytes(original)
        with self.assertRaises(ValueError):dense.validate_surface(self.output,1)
        (self.output/"unexpected.txt").write_text("ENGINE TEST extra")
        with self.assertRaises(ValueError):dense.validate_surface(self.output,2048)

    def test_symlinks_and_cancelled_publication_do_not_publish_members(self):
        texture=self.output/"texture_1001.png";texture.rename(self.root/"outside.png");texture.symlink_to(self.root/"outside.png")
        with self.assertRaises(ValueError):dense.validate_surface(self.output,2048)
        event=threading.Event();event.set();destination=self.root/"cancelled.zip"
        with self.assertRaises(InterruptedError):dense._bundle(self.output,[texture.name],destination,event,time.monotonic()+5)
        if destination.exists():
            with zipfile.ZipFile(destination) as result:self.assertEqual(result.namelist(),[])

    def test_actual_solved_camera_records_must_bind_to_selected_images(self):
        inputs=[{"filename":name+".jpg","asset_id":name} for name in "abc"]
        path,value=camera_record(self.root/"cache",inputs)
        record,stats=dense._registered(self.root/"cache",inputs,True)
        self.assertEqual(record,path);self.assertEqual(stats["registered_images"],3)
        value["poses"][0]["pose"]["transform"]["rotation"][0]="2";path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):dense._registered(self.root/"cache",inputs,True)
        value["poses"][0]["pose"]["transform"]["rotation"][0]="1";value["views"][0]["path"]="/outside/not-selected.jpg";path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):dense._registered(self.root/"cache",inputs,True)

    def test_live_scratch_budget_rejects_overflow_and_symbolic_links(self):
        scratch=self.root/"scratch";scratch.mkdir();(scratch/"file").write_bytes(b"12345")
        with patch.object(dense,"MAX_CACHE_BYTES",4),self.assertRaises(RuntimeError):dense._scratch_budget(scratch)
        (scratch/"file").unlink();(scratch/"link").symlink_to(self.output,target_is_directory=True)
        with self.assertRaises(RuntimeError):dense._scratch_budget(scratch)


if __name__=="__main__":unittest.main()
