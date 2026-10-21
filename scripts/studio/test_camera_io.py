"""Calibrated camera imports checked by independent source reprojection.

Fixtures here are constructed mathematical cameras, not production shots.
The JavaScript tests execute the real file transport helper used by the UI.
"""

import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import unittest

import camera_io


HERE = Path(__file__).resolve().parent


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def normalize(a):
    return [v / math.sqrt(dot(a, a)) for v in a]


def matrix_vector(matrix, vector):
    return [dot(row, vector) for row in matrix]


def transpose(matrix):
    return [list(row) for row in zip(*matrix)]


def rodrigues(axis, angle):
    """Independent axis-angle fixture, not the imported quaternion formula."""
    x, y, z = normalize(axis)
    k = [[0, -z, y], [z, 0, -x], [-y, x, 0]]
    outer = [[a*b for b in (x, y, z)] for a in (x, y, z)]
    return [[(1 if i == j else 0)*math.cos(angle) + outer[i][j]*(1-math.cos(angle))
             + k[i][j]*math.sin(angle) for j in range(3)] for i in range(3)]


def canonical_project(camera, point, width, height):
    """Consumer-side analytic pinhole projection, independent of importer."""
    forward = normalize([b-a for a, b in zip(camera["position"], camera["target"])])
    up = [0, 1, 0] if abs(forward[2]) > .999 else [0, 0, 1]
    r = normalize(cross(forward, up))
    u = cross(r, forward)
    angle = math.radians(camera["roll"])
    right = [r[i]*math.cos(angle)+u[i]*math.sin(angle) for i in range(3)]
    up = [u[i]*math.cos(angle)-r[i]*math.sin(angle) for i in range(3)]
    relative = [point[i]-camera["position"][i] for i in range(3)]
    depth = dot(relative, forward)
    fy = height/(2*math.tan(math.radians(camera["fov"])/2))
    return [width*(.5+camera["shift_x"])+fy*camera["focal_ratio"]*dot(relative, right)/depth,
            height*(.5-camera["shift_y"])-fy*dot(relative, up)/depth]


def fspy_state(width=1200, height=800, rotation=None, center=None):
    rotation = rotation or rodrigues([1, 2, 3], .71)
    center = center or [2, -4, 3]
    transform = [rotation[i]+[center[i]] for i in range(3)]+[[0, 0, 0, 1]]
    view = [row+[-dot(row, center)] for row in transpose(rotation)]+[[0, 0, 0, 1]]
    f = 1.7
    return {"cameraParameters": {"principalPoint": {"x": .12, "y": -.08},
            "cameraTransform": {"rows": transform}, "viewTransform": {"rows": view},
            "horizontalFieldOfView": 2*math.atan(1/f),
            "verticalFieldOfView": 2*math.atan(height/(width*f)),
            "relativeFocalLength": f, "imageWidth": width, "imageHeight": height},
            "calibrationSettingsBase": {"referenceDistanceAxis": None}}


def fspy_bytes(state=None, image=b"opaque image bytes; never decoded"):
    encoded = json.dumps(state or fspy_state(), allow_nan=False).encode()
    return b"fspy" + struct.pack("<III", 1, len(encoded), len(image)) + encoded + image


def fspy_payload(state=None):
    return {"format": "fspy_json", "name": "ENGINE_TEST_camera.json", "text": json.dumps(state or fspy_state())}


def colmap_payload(model="PINHOLE", params="950 850 610 390", axis=(1, 2, -1), angle=.83, name="shot one.png"):
    axis = normalize(axis)
    qw = math.cos(angle/2)
    qv = [v*math.sin(angle/2) for v in axis]
    pose = "19 " + " ".join(format(v, ".17g") for v in [qw]+qv+[1.1, -.4, 2.8]) + " 42 " + name
    return {"format": "colmap", "cameras_text": "# cameras\n42 %s 1200 800 %s\n" % (model, params),
            "images_text": "# images\n"+pose+"\n20 30 -1 200 300 91\n"}


class FSpyTests(unittest.TestCase):
    def test_binary_container_and_json_export_have_identical_camera(self):
        binary = fspy_bytes()
        a = camera_io.import_camera({"format": "fspy", "data_base64": base64.b64encode(binary).decode()}, 1200, 800)
        b = camera_io.import_camera(fspy_payload(), 1200, 800)
        self.assertEqual(a["cameras"][0]["camera"], b["cameras"][0]["camera"])
        self.assertEqual(a["cameras"][0]["source"]["sha256"], hashlib.sha256(binary).hexdigest())
        self.assertEqual(a["cameras"][0]["source"]["embedded_image_bytes"], 33)
        self.assertTrue(any("not imported or decoded" in text for text in a["warnings"]))
        exported = fspy_state()["cameraParameters"]
        self.assertEqual(camera_io.import_camera(fspy_payload(exported), 1200, 800)["cameras"][0]["camera"], b["cameras"][0]["camera"])

    def test_source_matrix_projection_preserved_for_landscape_and_portrait(self):
        for width, height in ((1200, 800), (800, 1200), (1000, 1000)):
            with self.subTest(width=width, height=height):
                state = fspy_state(width, height)
                params = state["cameraParameters"]
                result = camera_io.import_camera(fspy_payload(state), width//2, height//2)["cameras"][0]
                source = params["cameraTransform"]["rows"]
                f = params["relativeFocalLength"]
                longest = max(width, height)
                for xyz in ([.2, .3, -2], [-.9, .4, -3], [.7, -.8, -4], [0, 0, -1]):
                    world = [dot(row, xyz+[1]) for row in source[:3]]
                    pp = params["principalPoint"]
                    expected = [(width/2+(f*xyz[0]/-xyz[2]+pp["x"])*longest/2)/2,
                                (height/2-(f*xyz[1]/-xyz[2]+pp["y"])*longest/2)/2]
                    actual = canonical_project(result["camera"], world, width//2, height//2)
                    for a, b in zip(actual, expected):
                        self.assertAlmostEqual(a, b, places=8)

    def test_roll_at_world_up_pole_and_nonzero_shift_are_preserved(self):
        state = fspy_state(rotation=rodrigues([0, 0, 1], .6))
        camera = camera_io.import_camera(fspy_payload(state), 1200, 800)["cameras"][0]["camera"]
        self.assertAlmostEqual(camera["roll"], math.degrees(.6))
        self.assertAlmostEqual(camera["shift_x"], .06)
        self.assertAlmostEqual(camera["shift_y"], -.06)
        for xyz in ([1, .5, -4], [-.4, -.3, -2]):
            source = state["cameraParameters"]["cameraTransform"]["rows"]
            point = [dot(row, xyz+[1]) for row in source[:3]]
            projected = canonical_project(camera, point, 1200, 800)
            self.assertAlmostEqual(projected[0], 672+1020*xyz[0]/-xyz[2], places=8)
            self.assertAlmostEqual(projected[1], 448-1020*xyz[1]/-xyz[2], places=8)

    def test_scale_and_y_up_transform_preserve_projection_when_geometry_matches(self):
        state = fspy_state()
        payload = {**fspy_payload(state), "scale": 2.5, "up_axis": "Y"}
        camera = camera_io.import_camera(payload, 1200, 800)["cameras"][0]["camera"]
        self.assertEqual(camera["position"], [5, -7.5, -10])
        source = state["cameraParameters"]["cameraTransform"]["rows"]
        xyz = [.4, -.2, -3]
        world = [dot(row, xyz+[1]) for row in source[:3]]
        point = [world[0]*2.5, -world[2]*2.5, world[1]*2.5]
        projected = canonical_project(camera, point, 1200, 800)
        self.assertAlmostEqual(projected[0], 672+1020*.4/3, places=8)
        self.assertAlmostEqual(projected[1], 448+1020*.2/3, places=8)

    def test_null_solve_and_non_rigid_or_inconsistent_transforms_rejected(self):
        for change in ("null", "shear", "reflection", "projective", "inverse", "lens"):
            with self.subTest(change=change):
                state = fspy_state()
                params = state["cameraParameters"]
                if change == "null": state["cameraParameters"] = None
                elif change == "shear": params["cameraTransform"]["rows"][0][1] += .1
                elif change == "reflection":
                    for row in params["cameraTransform"]["rows"][:3]: row[0] *= -1
                elif change == "projective": params["cameraTransform"]["rows"][3][0] = .1
                elif change == "inverse": params["viewTransform"]["rows"][0][3] += .1
                elif change == "lens": params["relativeFocalLength"] *= 2
                with self.assertRaises(ValueError): camera_io.import_camera(fspy_payload(state), 1200, 800)

    def test_container_lengths_magic_version_and_base64_rejected(self):
        good = fspy_bytes()
        cases = [b"", b"bad!"+good[4:], good[:4]+struct.pack("<I", 2)+good[8:], good[:-1], good+b"x",
                 good[:8]+struct.pack("<I", 2**32-1)+good[12:]]
        for data in cases:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                camera_io.import_camera({"format":"fspy", "data_base64":base64.b64encode(data).decode()},1200,800)
        with self.assertRaises(ValueError): camera_io.import_camera({"format":"fspy", "data_base64":"invalid $$$"})

    def test_json_duplicate_nonfinite_depth_and_nonutf8_rejected(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', '['*35+'0'+']'*35, '{"x":"\ud800"}'):
            with self.subTest(text=repr(text)), self.assertRaises(ValueError):
                camera_io.import_camera({"format":"fspy_json", "text":text})
        data=b"fspy"+struct.pack("<III",1,1,0)+b"\xff"
        with self.assertRaises(ValueError): camera_io.import_camera({"format":"fspy", "data_base64":base64.b64encode(data).decode()})

    def test_aspect_crop_and_invalid_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError, "aspect"): camera_io.import_camera(fspy_payload(), 1280, 720)
        for change in ({"scale":float("inf")}, {"scale":True}, {"scale":0}, {"up_axis":"X"}, {"up_axis":[]}, {"path":"/private/file"}):
            with self.subTest(change=change), self.assertRaises(ValueError): camera_io.import_camera({**fspy_payload(), **change},1200,800)
        with self.assertRaisesRegex(ValueError, "position"): camera_io.import_camera({**fspy_payload(), "scale":1000},1200,800)


class ColmapTests(unittest.TestCase):
    def test_noncontiguous_ids_names_and_independent_rodrigues_reprojection(self):
        payload=colmap_payload()
        result=camera_io.import_camera(payload,1200,800)
        item=result["cameras"][0]
        self.assertEqual((item["id"],item["source"]["camera_id"],item["name"]),("19",42,"shot one.png"))
        self.assertEqual(result["statistics"],{"cameras":1,"images":1,"observations":2})
        rotation=rodrigues([1,2,-1],.83)
        for camera_point in ([.1,.2,3],[-1,.7,5],[1,-.3,4],[0,0,2]):
            relative=[camera_point[i]-[1.1,-.4,2.8][i] for i in range(3)]
            world=matrix_vector(transpose(rotation),relative)
            actual=canonical_project(item["camera"],world,1200,800)
            self.assertAlmostEqual(actual[0],950*camera_point[0]/camera_point[2]+610,places=8)
            self.assertAlmostEqual(actual[1],850*camera_point[1]/camera_point[2]+390,places=8)

    def test_camera_local_y_and_z_flip_without_changing_source_world(self):
        payload={"format":"colmap","cameras_text":"7 SIMPLE_PINHOLE 1200 800 900 600 400\n",
                 "images_text":"42 1 0 0 0 0 0 0 7 /private/not-opened.png\n\n"}
        camera=camera_io.import_camera(payload,1200,800)["cameras"][0]["camera"]
        self.assertEqual(camera["position"],[0,0,0])
        self.assertEqual(camera["target"],[0,0,1])
        # Trigonometric roundtrips differ by one ULP across Python/libm builds.
        for actual, expected in zip(canonical_project(camera,[1,2,4],1200,800),[825,850]):
            self.assertAlmostEqual(actual, expected, places=10)

    def test_empty_observation_lines_and_multiple_poses(self):
        payload=colmap_payload()
        payload["images_text"]="1 1 0 0 0 0 0 0 42 first.png\n\n# second\n90 1 0 0 0 1 0 0 42 second.png\n\n"
        result=camera_io.import_camera(payload,1200,800)
        self.assertEqual([c["id"] for c in result["cameras"]],["1","90"])
        self.assertEqual(result["cameras"][1]["camera"]["position"],[-1,0,0])
        self.assertEqual(result["statistics"]["observations"],0)

    def test_quaternion_sign_equivalence_and_small_export_roundoff(self):
        payload=colmap_payload()
        first=camera_io.import_camera(payload,1200,800)["cameras"][0]["camera"]
        lines=payload["images_text"].splitlines()
        tokens=lines[1].split(maxsplit=9)
        tokens[1:5]=[str(-float(x)) for x in tokens[1:5]]
        lines[1]=" ".join(tokens)
        payload["images_text"]="\n".join(lines)+"\n"
        self.assertEqual(camera_io.import_camera(payload,1200,800)["cameras"][0]["camera"],first)

    def test_unsupported_distortion_and_skew_never_silently_ignored(self):
        for model,params in (("SIMPLE_RADIAL","900 600 400 0"),("OPENCV","900 900 600 400 .1 .01 0 0"),
                             ("OPENCV_FISHEYE","900 900 600 400 0 0 0 0"),("SKEWED_PINHOLE","900 900 600 400 0")):
            with self.subTest(model=model),self.assertRaisesRegex(ValueError,"never discarded"):
                camera_io.import_camera(colmap_payload(model=model,params=params),1200,800)

    def test_invalid_pose_observation_record_or_missing_camera_rejected(self):
        good=colmap_payload()
        cases=["19 0 0 0 0 0 0 0 42 shot.png\n\n","19 1 0 0 0 0 0 0 99 shot.png\n\n",
               "19 1 0 0 0 0 0 0 42 shot.png\n","19 1 0 0 0 0 0 0 42 shot.png\n1 2\n",
               "19 1 0 0 0 0 0 0 42 shot.png\n1 nan 2\n","19 1 0 0 0 0 0 0 42 shot.png\n1 2 -2\n"]
        for text in cases:
            with self.subTest(text=text),self.assertRaises(ValueError): camera_io.import_camera({**good,"images_text":text},1200,800)
        pose="19 1 0 0 0 0 0 0 42 shot.png\n\n"
        with self.assertRaisesRegex(ValueError,"unique"): camera_io.import_camera({**good,"images_text":pose+pose},1200,800)
        with self.assertRaisesRegex(ValueError,"unique"): camera_io.import_camera({**good,"cameras_text":good["cameras_text"]*2},1200,800)

    def test_camera_and_pose_limits(self):
        good=colmap_payload()
        poses="".join("%s 1 0 0 0 0 0 0 42 shot.png\n\n"%i for i in range(1,130))
        with self.assertRaisesRegex(ValueError,"128"): camera_io.import_camera({**good,"images_text":poses},1200,800)

    def test_utf8_bom_and_crlf_preserve_exact_text_provenance(self):
        payload=colmap_payload()
        payload["cameras_text"]="\ufeff"+payload["cameras_text"].replace("\n","\r\n")
        payload["images_text"]="\ufeff"+payload["images_text"].replace("\n","\r\n")
        source=camera_io.import_camera(payload,1200,800)["cameras"][0]["source"]
        self.assertEqual(source["cameras_sha256"],hashlib.sha256(payload["cameras_text"].encode()).hexdigest())
        self.assertEqual(source["images_sha256"],hashlib.sha256(payload["images_text"].encode()).hexdigest())


class BrownMathTests(unittest.TestCase):
    def test_forward_known_hand_computed_point_and_inverse(self):
        coefficients=[.1,-.02,.003,-.004,.005]
        # x=.2,y=-.3,r2=.13, radial=1.012672985.
        expected=[.2*1.012672985+2*.003*.2*(-.3)-.004*(.13+2*.04),
                  -.3*1.012672985+.003*(.13+2*.09)+2*(-.004)*.2*(-.3)]
        point=camera_io.brown_distort_point(.2,-.3,coefficients)
        for a,b in zip(point,expected):self.assertAlmostEqual(a,b,places=12)
        inverse=camera_io.brown_undistort_point(*point,coefficients)
        self.assertAlmostEqual(inverse[0],.2,places=9)
        self.assertAlmostEqual(inverse[1],-.3,places=9)

    def test_inverse_is_reprojected_over_grid(self):
        coefficients=[-.12,.025,.001,-.002,.003]
        for ix in range(-5,6):
            for iy in range(-5,6):
                x,y=ix*.12,iy*.12
                distorted=camera_io.brown_distort_point(x,y,coefficients)
                undistorted=camera_io.brown_undistort_point(*distorted,coefficients)
                self.assertAlmostEqual(undistorted[0],x,places=8)
                self.assertAlmostEqual(undistorted[1],y,places=8)

    def test_folds_nonfinite_and_unsupported_models_rejected(self):
        with self.assertRaises(ValueError):camera_io.brown_undistort_point(.8,0,[-1,0,0,0,0])
        for values in ([0]*4,[0]*6,[0,0,0,0,float("nan")],[True,0,0,0,0]):
            with self.assertRaises(ValueError):camera_io.brown_distort_point(.2,.3,values)


@unittest.skipUnless(shutil.which("node"), "Node is required for actual UI transport execution.")
class JavaScriptTransportTests(unittest.TestCase):
    def run_helper(self,files,mode="fspy",**options):
        script="""const fs=require('fs'),vm=require('vm');global.window={};
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
const spec=JSON.parse(fs.readFileSync(0,'utf8'));
const files=spec.files.map(item=>{const bytes=Buffer.from(item.data,'base64');return {name:item.name,size:bytes.length,arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.length)}});
window.CinematicumCameraIO.readFiles(files,spec.mode,spec.scale,spec.up_axis).then(v=>process.stdout.write(JSON.stringify(v))).catch(e=>{process.stderr.write(e.message);process.exitCode=1});"""
        process=subprocess.run([shutil.which("node"),"-e",script,str(HERE/"web"/"camera-io-ui.js")],
                               input=json.dumps({"files":files,"mode":mode,"scale":options.get("scale",1),"up_axis":options.get("up_axis","Z")}),
                               text=True,capture_output=True,timeout=15)
        if process.returncode:raise ValueError(process.stderr)
        return json.loads(process.stdout)

    def test_actual_binary_file_transport_preserves_bytes_before_backend_import(self):
        data=fspy_bytes(image=bytes(range(256)))
        payload=self.run_helper([{"name":"calibrated.fspy","data":base64.b64encode(data).decode()}])
        self.assertEqual(base64.b64decode(payload["data_base64"]),data)
        result=camera_io.import_camera(payload,1200,800)
        self.assertEqual(result["cameras"][0]["source"]["sha256"],hashlib.sha256(data).hexdigest())

    def test_actual_json_transport_retains_duplicates_for_backend_to_reject(self):
        data=b'{"cameraParameters":null,"cameraParameters":null}'
        payload=self.run_helper([{"name":"camera.json","data":base64.b64encode(data).decode()}])
        self.assertEqual(payload["text"],data.decode())
        with self.assertRaisesRegex(ValueError,"Duplicate"):camera_io.import_camera(payload,1200,800)

    def test_actual_text_decoder_keeps_bom_for_exact_source_hash(self):
        data=("\ufeff"+json.dumps(fspy_state(),indent=2).replace("\n","\r\n")).encode()
        payload=self.run_helper([{"name":"camera.json","data":base64.b64encode(data).decode()}])
        self.assertEqual(payload["text"].encode(),data)
        source=camera_io.import_camera(payload,1200,800)["cameras"][0]["source"]
        self.assertEqual(source["sha256"],hashlib.sha256(data).hexdigest())

    def test_colmap_file_order_does_not_confuse_camera_and_image_inputs(self):
        source=colmap_payload()
        files=[{"name":"images.txt","data":base64.b64encode(source["images_text"].encode()).decode()},
               {"name":"cameras.txt","data":base64.b64encode(source["cameras_text"].encode()).decode()}]
        payload=self.run_helper(files,"colmap",scale=2,up_axis="Y")
        self.assertEqual(payload,{**source,"scale":2,"up_axis":"Y"})
        self.assertEqual(camera_io.import_camera(payload,1200,800)["statistics"]["images"],1)

    def test_file_transport_rejects_missing_files_bad_utf8_and_wrong_names(self):
        for files,mode in (([],"fspy"),([{"name":"bad.json","data":"/w=="}],"fspy"),
                           ([{"name":"cameras.txt","data":""},{"name":"elsewhere.txt","data":""}],"colmap")):
            with self.subTest(files=files),self.assertRaises(ValueError):self.run_helper(files,mode)

    def test_actual_scene_view_projection_preserves_imported_calibration(self):
        cases=[]
        for width,height in ((1200,800),(800,1200)):
            state=fspy_state(width,height)
            camera=camera_io.import_camera(fspy_payload(state),width,height)["cameras"][0]["camera"]
            matrix=state["cameraParameters"]["cameraTransform"]["rows"]
            points=[matrix_vector(matrix[:3],list(p)+[1]) for p in ([.2,.3,-2],[-.6,.7,-4],[.7,-.3,-3])]
            cases.append({"camera":camera,"width":width,"height":height,"points":points,
                          "expected":[canonical_project(camera,p,width,height) for p in points]})
        payload=colmap_payload()
        camera=camera_io.import_camera(payload,1200,800)["cameras"][0]["camera"]
        rotation=rodrigues([1,2,-1],.83)
        local=[[.3,.2,2],[-.4,.8,4]]
        points=[matrix_vector(transpose(rotation),[p[i]-[1.1,-.4,2.8][i] for i in range(3)]) for p in local]
        cases.append({"camera":camera,"width":1200,"height":800,"points":points,
                      "expected":[[950*p[0]/p[2]+610,850*p[1]/p[2]+390] for p in local]})
        script="""const fs=require('fs'),vm=require('vm');global.window={};
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(cases.map(c=>{const m=window.CinematicumSceneEditor.cameraProjection(c.camera,c.width,c.height);return c.points.map(p=>{const v=[0,1,2,3].map(i=>m[i]*p[0]+m[4+i]*p[1]+m[8+i]*p[2]+m[12+i]);return [(v[0]/v[3]+1)*c.width/2,(1-v[1]/v[3])*c.height/2]})})));"""
        process=subprocess.run([shutil.which("node"),"-e",script,str(HERE/"web"/"scene-editor.js")],
                               input=json.dumps(cases),text=True,capture_output=True,timeout=15,check=True)
        actual=json.loads(process.stdout)
        for case,projected in zip(cases,actual):
            for expected,result in zip(case["expected"],projected):
                for a,b in zip(expected,result):self.assertAlmostEqual(a,b,places=7)


if __name__ == "__main__":
    unittest.main()
