"""Geometry admission and viewport parity tests; no fixture is render proof."""

import ast
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock

import scene
import spatial_import as spatial
import test_scene as scene_fixture


TRIANGLE = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"


def imported(text=TRIANGLE, **kwargs):
    return spatial.import_obj({"name": "ENGINE_TEST_geometry.obj", "obj": text, **kwargs})


def normal_at(mesh, face, corner):
    return mesh["normals"][mesh["normal_indices"][face][corner]]


def signed_area(points):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1])) / 2


class ObjImportTests(unittest.TestCase):
    def test_triangle_is_real_indexed_geometry_with_exact_source_digest(self):
        text = "\ufeff# Source bytes retain the BOM and CRLF\r\n" + TRIANGLE
        result = imported(text)
        mesh = result["objects"][0]["mesh"]
        self.assertEqual(mesh["vertices"], [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        self.assertEqual(mesh["triangles"], [[0, 1, 2]])
        self.assertEqual(normal_at(mesh, 0, 0), [0., 0., 1.])
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(mesh["source"]["sha256"], result["source"]["sha256"])
        self.assertEqual(spatial.validate_mesh(mesh), mesh)
        self.assertEqual(result["statistics"]["triangles"], 1)
        self.assertFalse(result["warnings"])

    def test_concave_polygon_ear_clipping_preserves_region_area_and_winding(self):
        points = [(0, 0), (3, 0), (3, 3), (2, 3), (2, 1), (1, 1), (1, 3), (0, 3)]
        for reverse in (False, True):
            indices = list(range(1, 9))
            if reverse:
                indices.reverse()
            text = "".join("v %s %s 0\n" % point for point in points) + "f " + " ".join(map(str, indices)) + "\n"
            mesh = imported(text)["objects"][0]["mesh"]
            triangles = [[mesh["vertices"][index] for index in face] for face in mesh["triangles"]]
            self.assertEqual(len(triangles), 6)
            self.assertAlmostEqual(sum(signed_area(triangle) for triangle in triangles), -7 if reverse else 7)
            for triangle in triangles:
                cx, cy = (sum(point[i] for point in triangle) / 3 for i in (0, 1))
                self.assertFalse(1 < cx < 2 and cy > 1, "A triangulated face must not cover the concave opening.")
                self.assertGreater(signed_area(triangle) * (-1 if reverse else 1), 0)

    def test_negative_indices_resolve_at_each_face_and_y_up_conversion_preserves_handedness(self):
        text = "v 0 0 0\nv 1 0 0\nv 0 2 0\nf -3 -2 -1\nv 9 9 9\n"
        mesh = imported(text, up_axis="Y", scale=2)["objects"][0]["mesh"]
        self.assertEqual(mesh["vertices"], [[0., -0., 0.], [2., -0., 0.], [0., -0., 4.]])
        self.assertEqual(normal_at(mesh, 0, 0), [0., -1., 0.])
        self.assertEqual(mesh["source"]["up_axis"], "Y")
        self.assertEqual(mesh["source"]["scale"], 2.)

    def test_corner_uvs_and_explicit_normals_do_not_collapse_at_seams(self):
        text = ("v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n"
                "vt 0 0\nvt 1 0\nvt 0 1\nvt .2 .7\n"
                "vn 0 0 3\nvn 0 5 0\n"
                "f 1/1/1 2/2/1 3/3/1\nf 1/4/2 4/3/2 2/2/2\n")
        mesh = imported(text)["objects"][0]["mesh"]
        self.assertEqual(mesh["triangles"][0][0], mesh["triangles"][1][0])
        self.assertNotEqual(mesh["uv_indices"][0][0], mesh["uv_indices"][1][0])
        self.assertEqual(mesh["uvs"][mesh["uv_indices"][1][0]], [.2, .7])
        self.assertEqual(normal_at(mesh, 0, 0), [0, 0, 1])
        self.assertEqual(normal_at(mesh, 1, 0), [0, 1, 0])

    def test_smoothing_groups_and_explicit_normals_are_preserved(self):
        vertices = "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n"
        for smooth in ("off", "1"):
            mesh = imported(vertices + "s " + smooth + "\nf 1 2 3\nf 1 4 2\n")["objects"][0]["mesh"]
            a, b = normal_at(mesh, 0, 0), normal_at(mesh, 1, 0)
            if smooth == "off":
                self.assertEqual((a, b), ([0, 0, 1], [0, 1, 0]))
            else:
                self.assertEqual(a, b)
                self.assertAlmostEqual(a[1], math.sqrt(.5), places=9)
                self.assertAlmostEqual(a[2], math.sqrt(.5), places=9)
        mesh = imported(vertices + "vn 1 0 0\ns 1\nf 1//1 2//1 3//1\nf 1 4 2\n")["objects"][0]["mesh"]
        self.assertEqual(normal_at(mesh, 0, 0), [1, 0, 0])

    def test_material_parts_are_editable_and_textures_produce_an_explicit_warning(self):
        text = ("mtllib colors.mtl\no Two materials\nv 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n"
                "usemtl Red\nf 1 2 3\nusemtl Blue\nf 1 4 2\n")
        mtl = ("newmtl Red\nKd 1 0 0\nPr .2\nNs 500\nPm .6\nmap_Kd /private/unreadable-image.png\n"
               "newmtl Blue\nKd 0 0 1\nNs 6\n")
        result = imported(text, materials={"colors.mtl": mtl})
        self.assertEqual(len(result["objects"]), 2)
        red, blue = result["objects"]
        self.assertEqual(red["material"], {"color": "#ff0000", "roughness": .2, "metallic": .6})
        self.assertEqual(blue["material"]["color"], "#0000ff")
        self.assertEqual(blue["material"]["roughness"], .5)
        self.assertNotEqual(red["id"], blue["id"])
        self.assertEqual(result["source"]["materials"]["colors.mtl"], hashlib.sha256(mtl.encode()).hexdigest())
        self.assertTrue(any("texture images are not imported or opened" in warning for warning in result["warnings"]))
        self.assertEqual([o["mesh"]["source"]["material"] for o in result["objects"]], ["Red", "Blue"])

    def test_missing_material_partial_uv_and_transparency_are_not_silent(self):
        text = "mtllib missing.mtl\n" + TRIANGLE.replace("f 1 2 3", "vt 0 0\nusemtl Glass\nf 1/1 2 3")
        result = imported(text, materials={"glass.mtl": "newmtl Glass\nKd .5 .5 .5\nd .25\n"})
        joined = " ".join(result["warnings"])
        self.assertIn("was not selected", joined)
        self.assertIn("transparency", joined)
        self.assertIn("no UV coordinates", joined)
        self.assertEqual(result["objects"][0]["mesh"]["uv_indices"], [[0, -1, -1]])

    def test_invalid_faces_indices_and_unsupported_geometry_are_rejected(self):
        cases = ["f 0 2 3", "f 1 2 4", "f -4 -2 -1", "f 1.0 2 3", "f 1 1 3", "f 1 2", "f 1/ 2 3",
                 "f 1// 2 3", "f 1/1 2 3", "f 1//1 2 3", "f 1/1/1/1 2 3", "l 1 2", "p 1",
                 "surf 0 1 0 1 1 2 3", "call /tmp/code.obj", "csh touch /tmp/owned", "f 1 2 3\\"]
        header = TRIANGLE.split("f ")[0]
        for face in cases:
            with self.subTest(face=face), self.assertRaises(ValueError):
                imported(header + face + "\n")
        bad_polygons = ["v 0 0 0\nv 1 1 0\nv 0 1 0\nv 1 0 0\nf 1 2 3 4\n",
                        "v 0 0 0\nv 1 0 0\nv 1 1 .3\nv 0 1 0\nf 1 2 3 4\n",
                        "v 0 0 0\nv 1 0 0\nv 2 0 0\nf 1 2 3\n"]
        for text in bad_polygons:
            with self.subTest(text=text), self.assertRaises(ValueError):
                imported(text)

    def test_malformed_numeric_data_untrusted_paths_and_payloads_are_rejected(self):
        cases = [{"obj": TRIANGLE.replace("v 1 0 0", "v nan 0 0")},
                 {"obj": TRIANGLE.replace("v 1 0 0", "v inf 0 0")},
                 {"obj": TRIANGLE.replace("v 1 0 0", "v 1e100000 0 0")},
                 {"obj": TRIANGLE.replace("v 1 0 0", "v 1 0 0 .5")},
                 {"obj": TRIANGLE + "vn 0 0 0\n"}, {"obj": TRIANGLE + "\x00"},
                 {"obj": TRIANGLE + "#\ud800"}, {"name": "../secret.obj"}, {"name": "file:///secret.obj"},
                 {"obj": "mtllib ../../secret.mtl\n" + TRIANGLE},
                 {"materials": {"/private/secret.mtl": "newmtl a\n"}},
                 {"scale": True}, {"scale": 0}, {"scale": math.nan}, {"scale": 10**400}, {"up_axis": []}, {"command": "anything"}]
        for changes in cases:
            payload = {"name": "test.obj", "obj": TRIANGLE, **changes}
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                spatial.import_obj(payload)

    def test_empty_and_oversized_sources_fail_before_geometry_work(self):
        for value in ("", "# Only a comment\n", "v 0 0 0\n"):
            with self.assertRaises(ValueError):
                imported(value)
        with self.assertRaisesRegex(ValueError, "file size"):
            imported("#" * (spatial.MAX_OBJ_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "file size"):
            imported(materials={"too-big.mtl": "#" * (spatial.MAX_MTL_BYTES + 1)})
        with self.assertRaisesRegex(ValueError, "too long"):
            imported("#" * (spatial.MAX_LINE_LENGTH + 1) + "\n" + TRIANGLE)
        with self.assertRaisesRegex(ValueError, "source vertices"):
            imported("v 0 0 0\n" * (spatial.MAX_VERTICES + 1) + "f 1 2 3\n")
        with self.assertRaisesRegex(ValueError, "corners"):
            imported(TRIANGLE.split("f ")[0] + "f " + " ".join(["1"] * 65))
        text = TRIANGLE.split("f ")[0] + "".join("g part%d\nf 1 2 3\n" % i for i in range(97))
        with self.assertRaisesRegex(ValueError, "parts"):
            imported(text)

    def test_canonical_mesh_validation_rejects_forgery_and_invalid_attributes(self):
        mesh = imported()["objects"][0]["mesh"]
        mutations = [lambda m: m["vertices"][0].__setitem__(0, .1),
                     lambda m: m["triangles"][0].__setitem__(0, True),
                     lambda m: m["triangles"][0].__setitem__(0, 400),
                     lambda m: m["normal_indices"][0].__setitem__(0, -1),
                     lambda m: m["normals"][0].__setitem__(0, .8),
                     lambda m: m.update(normals=[]), lambda m: m.update(version=True),
                     lambda m: m.update(script="not evaluated"),
                     lambda m: m["source"].update(name="../../other.obj")]
        for change in mutations:
            candidate = copy.deepcopy(mesh)
            change(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                spatial.validate_mesh(candidate)

    def test_mesh_digest_survives_real_javascript_json_transport_and_rejects_changes(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is required to exercise actual JavaScript JSON transport.")
        from test_spatial_blender import OBJ, MTL
        imports = [spatial.import_obj({"name": "ENGINE_TEST.obj", "obj": OBJ,
                                      "materials": {"ENGINE_TEST.mtl": MTL}}),
                   imported(up_axis="Y"),
                   imported("v -0.0 1e-7 0\nv 1.2345678901234567 0 0\nv 0 1 0\n"
                            "vt -0.0 1e-7\nvt 1 0\nvt 0 1\nvn -0.0 0 1\n"
                            "f 1/1/1 2/2/1 3/3/1\n")]
        originals = []
        for result in imports:
            spec = scene.default_scene(160, 90)
            spec["objects"] = result["objects"]
            originals.append(scene.validate_scene(spec))
        script = """const fs=require('fs');let scenes=JSON.parse(fs.readFileSync(0,'utf8'));
// The browser clones recipes for history and serializes them again for Save.
scenes=JSON.parse(JSON.stringify(scenes));process.stdout.write(JSON.stringify(scenes));"""
        process = subprocess.run([node, "-e", script], input=json.dumps(originals),
                                 text=True, capture_output=True, check=True, timeout=5)
        returned = json.loads(process.stdout)
        self.assertEqual(len(returned), len(originals))
        for before, after in zip(originals, returned):
            normalized = scene.validate_scene(after)
            self.assertEqual(normalized, before)
            for original, received in zip(before["objects"], normalized["objects"]):
                self.assertEqual(spatial._json_bytes(received["mesh"]), spatial._json_bytes(original["mesh"]))
                self.assertEqual(received["mesh"]["source"], original["mesh"]["source"])
                for field in ("vertices", "normals", "uvs"):
                    self.assertTrue(all(math.copysign(1, value) == 1 for row in received["mesh"][field]
                                        for value in row if value == 0), "Canonical zero must have one representation")
                changed = copy.deepcopy(received["mesh"])
                changed["vertices"][0][0] += .125
                with self.assertRaisesRegex(ValueError, "SHA-256 digest"):
                    spatial.validate_mesh(changed)

    def test_scene_accepts_mesh_animation_but_enforces_total_geometry_budget(self):
        result = imported()
        spec = scene.default_scene(160, 90)
        spec["objects"] = result["objects"]
        spec["objects"][0]["keyframes"] = [{"frame": 1, "interpolation": "ease_in"}, {"frame": 9, "position": [4, 0, 0]}]
        validated = scene.validate_scene(spec)
        self.assertEqual(scene.pose_at(validated["objects"][0], 5)["position"], [1., 0., 0.])
        self.assertEqual(validated["objects"][0]["mesh"], result["objects"][0]["mesh"])
        with mock.patch.object(spatial, "MAX_GEOMETRY_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "geometry limit|geometry together"):
                scene.validate_scene(spec)
        spec["objects"][0]["type"] = "cube"
        with self.assertRaisesRegex(ValueError, "Only mesh"):
            scene.validate_scene(spec)

    def test_viewport_triangle_and_corner_normal_buffers_match_canonical_geometry(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is required to compare viewport geometry.")
        mesh = imported("v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\ns 1\nf 1 2 3\nf 1 4 2\n")["objects"][0]["mesh"]
        script = """const fs=require('fs'),vm=require('vm');global.window={};vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));const api=window.CinematicumSceneEditor,mesh=JSON.parse(fs.readFileSync(0,'utf8')),data=api.meshGeometry(mesh);data.bounds=api.geometryBounds(data.vertices);const hit=api.intersectGeometry(data,{position:[0,0,2],rotation:[0,0,90],scale:[2,3,.5]},{origin:[-.6,.4,10],direction:[0,0,-1]});const miss=api.intersectGeometry(data,{position:[0,0,2],rotation:[0,0,90],scale:[2,3,.5]},{origin:[4,4,10],direction:[0,0,-1]});console.log(JSON.stringify({vertices:[...data.vertices],normals:[...data.normals],bounds:data.bounds,hit,miss}));"""
        result = subprocess.run([node, "-e", script, str(Path(__file__).parent / "web" / "scene-editor.js")],
                                input=json.dumps(mesh), text=True, capture_output=True, timeout=10, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["vertices"], [value for face in mesh["triangles"] for index in face for value in mesh["vertices"][index]])
        expected = [value for face in mesh["normal_indices"] for index in face for value in mesh["normals"][index]]
        for actual, expected in zip(data["normals"], expected):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertEqual(data["bounds"]["center"], [.5, .5, .5])
        self.assertAlmostEqual(data["hit"], 8)
        self.assertIsNone(data["miss"])


class SpatialRenderBoundaryTests(unittest.TestCase):
    """Reuse the explicit process fixture only for publication/command boundaries."""

    setUp = scene_fixture.SceneRenderingTests.setUp
    tearDown = scene_fixture.SceneRenderingTests.tearDown
    execute_fixture = scene_fixture.SceneRenderingTests.execute_fixture
    run_render = scene_fixture.SceneRenderingTests.run_render

    def test_mesh_recipe_and_rational_timebase_reach_renderer_and_provenance(self):
        spec = scene.default_scene(160, 90)
        spec["frame_end"] = 9
        spec["objects"] = imported()["objects"]
        result = self.run_render(spec, fps={"numerator": 24000, "denominator": 1001})
        provenance = result["provenance"]
        self.assertEqual((provenance["mesh_objects"], provenance["mesh_vertices"], provenance["mesh_triangles"]), (1, 3, 1))
        self.assertEqual(provenance["mesh_geometry_sha256"], [spec["objects"][0]["mesh"]["sha256"]])
        self.assertEqual(provenance["mesh_source_sha256"], [hashlib.sha256(TRIANGLE.encode()).hexdigest()])
        self.assertEqual(provenance["frame_rate"], {"numerator": 24000, "denominator": 1001})
        self.assertEqual(self.calls[1][self.calls[1].index("-framerate") + 1], "24000/1001")
        script = scene._build_script(scene.validate_scene(spec), "/owned/model.blend", "/owned/frames", provenance["frame_rate"], 1, 3)
        constants = scene_fixture.script_constants(script)
        self.assertEqual(constants["FPS"], 24)
        assignments = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(script).body
                       if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "FPS_BASE"}
        self.assertAlmostEqual(assignments["FPS_BASE"], 1.001)
        self.assertEqual(constants["SPEC"]["objects"][0]["mesh"], spec["objects"][0]["mesh"])
        self.assertIn("mesh_data.from_pydata", script)
        self.assertIn("normals_split_custom_set", script)
        self.assertNotIn("wm.obj_import", script)


if __name__ == "__main__":
    unittest.main()
