"""Scene recipes and owned-render boundaries. Mock bytes are test fixtures only."""

import ast
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

import scene
from adapters import AdapterCancelled, AdapterError


def recipe():
    value = scene.default_scene(160, 90)
    value["frame_end"] = 9
    value["samples"] = 4
    value["objects"] = [{"id": "object_1", "name": "Authored cube", "type": "cube",
                         "position": [0, 0, 1], "rotation": [0, 0, 0], "scale": [1, 1, 1],
                         "material": {"color": "#c07c42", "roughness": .5, "metallic": .1},
                         "keyframes": [{"frame": 9, "position": [4, 0, 1], "rotation": [0, 0, 360], "scale": [2, 1, 1]}]}]
    return value


def script_constants(script):
    constants = {}
    for statement in ast.parse(script).body:
        if isinstance(statement, ast.Assign) and isinstance(statement.targets[0], ast.Name):
            name = statement.targets[0].id
            if name in {"BLEND_PATH", "FRAMES", "FPS", "START", "END"}:
                constants[name] = ast.literal_eval(statement.value)
            elif name == "SPEC":
                constants[name] = json.loads(ast.literal_eval(statement.value.args[0]))
    return constants


class SceneRecipeTests(unittest.TestCase):
    def test_recipe_normalizes_independently_and_project_dimensions_win(self):
        original = recipe()
        normalized = scene.validate_scene(original, width=320, height=180)
        self.assertEqual((normalized["width"], normalized["height"]), (320, 180))
        self.assertEqual(original["width"], 160)
        normalized["objects"][0]["position"][0] = 5
        self.assertEqual(original["objects"][0]["position"][0], 0)
        self.assertEqual(len(scene.default_scene()["objects"]), 0)

    def test_unknown_code_paths_nonfinite_and_resource_excess_are_rejected(self):
        mutations = [lambda r: r.update(script="print('not allowed')"),
                     lambda r: r["objects"][0].update(path="/tmp/not-an-asset.blend"),
                     lambda r: r["objects"][0]["position"].__setitem__(0, float("nan")),
                     lambda r: r["objects"][0]["scale"].__setitem__(0, 0),
                     lambda r: r.update(frame_end=7201),
                     lambda r: r.update(width=8192, height=8192),
                     lambda r: r.update(version=True),
                     lambda r: r.update(objects=r["objects"] * 97),
                     lambda r: r["objects"][0].update(type="arbitrary-python"),
                     lambda r: r["camera"].update(position=r["camera"]["target"])]
        for change in mutations:
            value = recipe()
            change(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                scene.validate_scene(value)

    def test_duplicate_ids_and_invalid_keyframes_fail(self):
        value = recipe()
        value["lights"][0]["id"] = "object_1"
        with self.assertRaisesRegex(ValueError, "unique"):
            scene.validate_scene(value)
        for keys in ([{"frame": 0}], [{"frame": 10}], [{"frame": 2}, {"frame": 2}], [{"frame": True}], [{"frame": 1, "expression": "x"}]):
            value = recipe()
            value["objects"][0]["keyframes"] = keys
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                scene.validate_scene(value)

    def test_pose_interpolates_from_base_without_shortest_angle_wrapping(self):
        obj = scene.validate_scene(recipe())["objects"][0]
        self.assertEqual(scene.pose_at(obj, 1)["position"], [0, 0, 1])
        midpoint = scene.pose_at(obj, 5)
        self.assertEqual(midpoint["position"], [2, 0, 1])
        self.assertEqual(midpoint["rotation"], [0, 0, 180])
        self.assertEqual(midpoint["scale"], [1.5, 1, 1])
        self.assertEqual(scene.pose_at(obj, 30)["rotation"], [0, 0, 360])
        obj["keyframes"].insert(0, {"frame": 1, "position": [-4, 0, 1], "rotation": [0, 0, 90], "scale": [1, 1, 1]})
        self.assertEqual(scene.pose_at(obj, 5)["position"], [0, 0, 1])

    def test_generated_python_treats_names_as_data_and_keeps_scene_recipe(self):
        value = recipe()
        value["objects"][0]["name"] = "Quoted ' scene; __import__('not_code')"
        normalized = scene.validate_scene(value)
        script = scene._build_script(normalized, "/owned/scene.blend", "/owned/frames", 24, 2, 4)
        compile(script, "generated-scene.py", "exec")
        values = script_constants(script)
        self.assertEqual(values["SPEC"], normalized)
        self.assertEqual((values["START"], values["END"], values["FPS"]), (2, 4, 24))
        self.assertEqual(values["BLEND_PATH"], "/owned/scene.blend")
        self.assertIn("CINEMATICUM Scene Recipe.json", script)
        self.assertIn("scene.cycles.device = 'CPU'", script)

    def test_saved_animation_is_linear_for_legacy_and_layered_actions(self):
        script = scene._build_script(scene.validate_scene(recipe()), "/owned/scene.blend", "/owned/frames", 24, 1, 9)
        tree = ast.parse(script)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "linearize_action")
        scope = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "scene-linearization", "exec"), scope)
        for layered in (False, True):
            keys = [SimpleNamespace(interpolation="BEZIER") for _ in range(3)]
            curve = SimpleNamespace(keyframe_points=keys, extrapolation="LINEAR")
            action = (SimpleNamespace(layers=[SimpleNamespace(strips=[SimpleNamespace(channelbags=[SimpleNamespace(fcurves=[curve])])])])
                      if layered else SimpleNamespace(fcurves=[curve]))
            scope["linearize_action"](SimpleNamespace(animation_data=SimpleNamespace(action=action)))
            self.assertEqual([key.interpolation for key in keys], ["LINEAR"] * 3)
            self.assertEqual(curve.extrapolation, "CONSTANT")
        with self.assertRaisesRegex(RuntimeError, "animation curves"):
            scope["linearize_action"](SimpleNamespace(animation_data=SimpleNamespace(action=SimpleNamespace(layers=[]))))
        self.assertLess(script.index("interpolate_action(obj, poses)\n    objects.append"), script.index("bpy.ops.wm.save_as_mainfile"))
        self.assertIn("scene.render.filepath = '//renders/frame_######'", script)

    def test_camera_light_keys_and_easing_share_exact_endpoint_semantics(self):
        value = recipe()
        value["camera"]["keyframes"] = [{"frame": 1, "interpolation": "ease_in"},
                                         {"frame": 9, "position": [15, -9, 6], "target": [0, 0, 3], "fov": 85}]
        value["lights"][0]["keyframes"] = [{"frame": 1, "interpolation": "constant"},
                                             {"frame": 9, "power": 2100, "size": 9}]
        normalized = scene.validate_scene(value)
        camera = normalized["camera"]
        self.assertEqual(scene.pose_at(camera, 5, "camera")["position"], [9, -9, 6])
        self.assertEqual(scene.pose_at(camera, 5, "camera")["fov"], 55)
        self.assertEqual(scene.pose_at(camera, 9, "camera")["fov"], 85)
        light = normalized["lights"][0]
        self.assertEqual(scene.pose_at(light, 8.999, "light")["power"], 1100)
        self.assertEqual(scene.pose_at(light, 9, "light")["power"], 2100)
        for mode, expected in (("linear", .25), ("constant", 0), ("ease_in", .0625),
                               ("ease_out", .4375), ("ease_in_out", .15625)):
            self.assertEqual(scene.easing(.25, mode), expected)

    def test_camera_light_animation_rejects_unsupported_and_invalid_values(self):
        cases = [("camera", {"frame": 2, "fov": 200}), ("camera", {"frame": 2, "fov": True}),
                 ("camera", {"frame": 2, "position": [0, 0, 0], "target": [0, 0, 0]}),
                 ("camera", {"frame": 2, "interpolation": "python:execute"}),
                 ("light", {"frame": 2, "power": -1}), ("light", {"frame": 2, "size": 0}),
                 ("light", {"frame": 2, "expression": "frame*2"})]
        for kind, key in cases:
            value = recipe()
            target = value["camera"] if kind == "camera" else value["lights"][0]
            target["keyframes"] = [key]
            with self.subTest(kind=kind, key=key), self.assertRaises(ValueError):
                scene.validate_scene(value)

    def test_blender_curve_handles_reproduce_polynomial_easing(self):
        source = scene._build_script(scene.validate_scene(recipe()), "/owned/scene.blend", "/owned/frames", 24, 1, 9)
        tree = ast.parse(source)
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in {"linearize_action", "action_curves", "interpolate_action", "recipe_poses", "pose_at"}]
        scope = {}
        exec(compile(ast.Module(body=functions, type_ignores=[]), "scene-generated-curves", "exec"), scope)
        for mode in scene.INTERPOLATIONS:
            points = [SimpleNamespace(co=[1., 2.], interpolation="LINEAR"), SimpleNamespace(co=[9., 10.], interpolation="LINEAR")]
            curve = SimpleNamespace(keyframe_points=points)
            owner = SimpleNamespace(animation_data=SimpleNamespace(action=SimpleNamespace(fcurves=[curve])))
            poses = [(1, {"frame": 1, "interpolation": mode}), (9, {"frame": 9})]
            scope["interpolate_action"](owner, poses)
            for t in (.125, .25, .5, .75, .875):
                if mode.startswith("ease_"):
                    left, right = points
                    actual = (1-t)**3*left.co[1] + 3*(1-t)**2*t*left.handle_right[1] + 3*(1-t)*t*t*right.handle_left[1] + t**3*right.co[1]
                    self.assertAlmostEqual(left.handle_right[0], 1+8/3)
                    self.assertAlmostEqual(right.handle_left[0], 9-8/3)
                else:
                    actual = 2 if mode == "constant" else 2+8*t
                    self.assertEqual(points[0].interpolation, "CONSTANT" if mode == "constant" else "LINEAR")
                self.assertAlmostEqual(actual, 2+8*scene.easing(t, mode), places=10)

    def test_javascript_python_and_generated_render_evaluate_identically(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is required to compare the authoring evaluator.")
        values = []
        for mode in scene.INTERPOLATIONS:
            value = recipe()
            value["objects"][0]["keyframes"].insert(0, {"frame": 1, "interpolation": mode})
            value["camera"]["keyframes"] = [{"frame": 1, "interpolation": mode}, {"frame": 9, "fov": 75, "position": [11, -5, 7]}]
            value["lights"][0]["keyframes"] = [{"frame": 1, "interpolation": mode}, {"frame": 9, "power": 1500, "size": 2, "position": [0, -2, 4]}]
            value = scene.validate_scene(value)
            for kind, item in (("object", value["objects"][0]), ("camera", value["camera"]), ("light", value["lights"][0])):
                for frame in (0, 1, 3, 5, 8.999, 9, 20):
                    values.append({"kind": kind, "item": item, "frame": frame, "expected": scene.pose_at(item, frame, kind)})
        script = "const fs=require('fs'),vm=require('vm');global.window={};vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));const rows=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(rows.map(r=>window.CinematicumSceneEditor.poseAt(r.item,r.frame,r.kind))));"
        output = subprocess.run([node, "-e", script, str(Path(__file__).parent / "web" / "scene-editor.js")],
                                input=json.dumps(values), text=True, capture_output=True, check=True, timeout=10)
        results = json.loads(output.stdout)
        generated = ast.parse(scene._build_script(scene.validate_scene(recipe()), "/owned/a.blend", "/owned/frames", 24, 1, 9))
        functions = [node for node in generated.body if isinstance(node, ast.FunctionDef) and node.name in {"recipe_poses", "pose_at"}]
        scope = {}
        exec(compile(ast.Module(body=functions, type_ignores=[]), "scene-render-evaluation", "exec"), scope)
        for row, actual in zip(values, results):
            self.assertEqual(actual, row["expected"])
            poses = scope["recipe_poses"](row["item"], scene.POSE_FIELDS[row["kind"]])
            self.assertEqual(scope["pose_at"](poses, row["frame"]), row["expected"])


class SceneRenderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def execute_fixture(self, argv, log_path, event, timeout, on_tick=lambda: None):
        """Checks adapter file boundaries; fixture bytes are never claimed as media."""
        self.calls.append(argv)
        if argv[0] == "/test/blender":
            values = script_constants(Path(argv[-1]).read_text())
            Path(values["BLEND_PATH"]).write_bytes(b"TEST-ONLY-BLEND-FIXTURE")
            for frame in range(values["START"], values["END"] + 1):
                (Path(values["FRAMES"]) / ("frame_%06d.png" % frame)).write_bytes(b"TEST-ONLY-FRAME")
            on_tick()
        else:
            Path(argv[-1]).write_bytes(b"TEST-ONLY-ENCODED-FIXTURE")

    def run_render(self, value=None, **kwargs):
        with mock.patch.object(scene, "find_blender", return_value="/test/blender"), \
                mock.patch.object(scene.shutil, "which", return_value="/test/ffmpeg"), \
                mock.patch.object(scene, "_run_owned", side_effect=self.execute_fixture):
            return scene.render_scene(value or recipe(), self.root, frame_start=2, frame_end=4, **kwargs)

    def test_owned_render_publishes_both_movie_and_reproducible_scene(self):
        progress = []
        result = self.run_render(progress=progress.append)
        self.assertTrue(Path(result["path"]).is_file())
        self.assertTrue(Path(result["scene_path"]).is_file())
        self.assertEqual(Path(result["path"]).parent, self.root.resolve())
        self.assertIn("--factory-startup", self.calls[0])
        self.assertIn("--disable-autoexec", self.calls[0])
        self.assertEqual(self.calls[1][self.calls[1].index("-frames:v") + 1], "3")
        self.assertEqual(result["provenance"]["frame_end"], 4)
        self.assertEqual(result["provenance"]["output_sha256"], scene._sha256(Path(result["path"])))
        self.assertEqual(progress[-1], 1)
        self.assertFalse(list(self.root.glob(".scene-*")))

    def test_empty_scene_and_pre_cancel_do_not_launch_process(self):
        with mock.patch.object(scene, "_run_owned") as run:
            with self.assertRaisesRegex(ValueError, "Add at least one"):
                scene.render_scene(scene.default_scene(), self.root)
            event = threading.Event()
            event.set()
            with self.assertRaises(AdapterCancelled):
                scene.render_scene(recipe(), self.root, cancel_event=event)
            run.assert_not_called()

    def test_missing_frames_refuse_without_publishing(self):
        original = self.execute_fixture

        def missing(argv, *args):
            original(argv, *args)
            if argv[0] == "/test/blender":
                values = script_constants(Path(argv[-1]).read_text())
                (Path(values["FRAMES"]) / "frame_000003.png").unlink()

        self.execute_fixture = missing
        with self.assertRaisesRegex(AdapterError, "scene frame 3"):
            self.run_render()
        self.assertFalse(list(self.root.iterdir()))

    def test_encode_failure_does_not_publish_scene_or_movie(self):
        original = self.execute_fixture

        def fail(argv, *args):
            if argv[0] != "/test/blender":
                raise AdapterError("encoding fixture failure")
            original(argv, *args)

        self.execute_fixture = fail
        with self.assertRaisesRegex(AdapterError, "encoding fixture failure"):
            self.run_render()
        self.assertFalse(list(self.root.iterdir()))


if __name__ == "__main__":
    unittest.main()
