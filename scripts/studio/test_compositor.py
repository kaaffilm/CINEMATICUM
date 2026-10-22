"""Decoded media checks for editable node graphs. Fixtures are not film footage."""
import copy
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
import zlib

from compositor import animation_value, compile_graph, node_params_at, validate_graph
from engine import probe_media, render_project, validate_project
from frame_preview import render_frame


def node(ident, kind, inputs=(), **params):
    return {"id": ident, "type": kind, "inputs": list(inputs), "params": params}


def graph(*nodes, output=None):
    return {"version": 1, "nodes": list(nodes), "output": output or nodes[-1]["id"]}


class GraphValidationTests(unittest.TestCase):
    def test_mask_tracking_provenance_is_bounded_preserved_and_does_not_execute(self):
        mask = node("mask", "mask", ["source"])
        mask["tracking_source"] = {"version": 1, "sha256": "a" * 64, "backend": "ffmpeg-template-correlation"}
        raw = graph(node("source", "source"), mask)
        normalized = validate_graph(raw)
        self.assertEqual(normalized["nodes"][1]["tracking_source"], mask["tracking_source"])
        normalized["nodes"][1]["tracking_source"]["backend"] = "changed"
        self.assertEqual(mask["tracking_source"]["backend"], "ffmpeg-template-correlation")
        unmarked = copy.deepcopy(raw); del unmarked["nodes"][1]["tracking_source"]
        self.assertEqual(compile_graph(raw, "image", "check"), compile_graph(unmarked, "image", "check"))
        invalid = [None, {}, {"version": True, "sha256": "a" * 64, "backend": "test"},
                   {"version": 1, "sha256": "not-a-digest", "backend": "test"},
                   {"version": 1, "sha256": "a" * 64, "backend": "x" * 161},
                   {"version": 1, "sha256": "a" * 64, "backend": "test", "command": "exec"}]
        for metadata in invalid:
            bad = copy.deepcopy(raw); bad["nodes"][1]["tracking_source"] = metadata
            with self.subTest(metadata=metadata), self.assertRaisesRegex(ValueError, "tracking_source"):
                validate_graph(bad)
        bad = copy.deepcopy(raw); bad["nodes"][0]["tracking_source"] = bad["nodes"][1]["tracking_source"]
        with self.assertRaisesRegex(ValueError, "tracking_source"):
            validate_graph(bad)

    @unittest.skipUnless(shutil.which("node"), "Node is required to compare the shipped inspector evaluator")
    def test_shipped_javascript_evaluator_matches_python_on_independent_path_channels(self):
        raw = node("mask", "mask", ["source"], shape="polygon")
        raw["animation"] = {
            "x": [{"frame": -4, "value": .2, "interpolation": "ease_out"},
                  {"frame": 0, "value": .5, "interpolation": "ease_in_out"}, {"frame": 8, "value": .9}],
            "points": [{"frame": 0, "value": [[.1, .85], [.5, .1], [.9, .85]], "interpolation": "ease_in"},
                       {"frame": 8, "value": [[.2, .7], [.7, .2], [.8, .9]]}],
        }
        normalized = validate_graph(graph(node("source", "source"), raw), animation_start=-4, animation_duration=9)
        item, frames = normalized["nodes"][1], [-10, -4, -2, 0, 2, 4, 7.5, 8, 20]
        script = """
const fs=require('fs'),vm=require('vm'),payload=JSON.parse(fs.readFileSync(0,'utf8')),sandbox={window:{}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(payload.source,'utf8'),sandbox);
const api=sandbox.window.CinematicumCompositor;
if(api.validate(payload.graph,{animationStart:-4,animationDuration:9}))throw Error('Valid saved animation rejected');
const wrong=JSON.parse(JSON.stringify(payload.graph));wrong.nodes[1].animation.points[1].value.pop();
if(!api.validate(wrong,{animationStart:-4,animationDuration:9}))throw Error('Mismatched polygon topology accepted');
process.stdout.write(JSON.stringify(payload.frames.map(frame=>api.paramsAt(payload.graph.nodes[1],frame))));
"""
        result = subprocess.run([shutil.which("node"), "-e", script], input=json.dumps({
            "source": str(Path(__file__).parent / "web" / "compositor-ui.js"), "graph": normalized, "frames": frames}),
            text=True, capture_output=True, check=True, timeout=10)
        values = json.loads(result.stdout)
        for frame, actual in zip(frames, values):
            expected = node_params_at(item, frame)
            self.assertAlmostEqual(actual["x"], expected["x"])
            for a, b in zip(actual["points"], expected["points"]):
                self.assertAlmostEqual(a[0], b[0])
                self.assertAlmostEqual(a[1], b[1])

    def test_independent_animation_domains_easing_and_implicit_base(self):
        animated = node("mask", "mask", ["source"], x=.3, y=.5)
        animated["animation"] = {
            "x": [{"frame": 8, "value": .9}, {"frame": -4, "value": .1, "interpolation": "constant"}],
            "y": [{"frame": 0, "value": .1, "interpolation": "ease_in"}, {"frame": 8, "value": .9}],
        }
        raw = graph(node("source", "source"), animated)
        before = copy.deepcopy(raw)
        normalized = validate_graph(raw, animation_start=-4, animation_duration=9)
        mask = normalized["nodes"][1]
        self.assertEqual(raw, before)
        self.assertEqual([key["frame"] for key in mask["animation"]["x"]], [-4, 8])
        self.assertEqual(node_params_at(mask, -1)["x"], .1)
        self.assertAlmostEqual(node_params_at(mask, 4)["x"], .6)
        self.assertAlmostEqual(node_params_at(mask, 4)["y"], .3)
        for mode, expected in (("linear", .25), ("constant", 0), ("ease_in", .0625),
                               ("ease_out", .4375), ("ease_in_out", .15625)):
            keys = [{"frame": 0, "value": 0, "interpolation": mode}, {"frame": 8, "value": 1}]
            self.assertAlmostEqual(animation_value(0, keys, 2), expected)
            self.assertEqual(animation_value(0, keys, 8), 1)
            self.assertEqual(animation_value(0, keys, -10), 0)
            self.assertEqual(animation_value(0, keys, 80), 1)

    def test_animation_validation_rejects_expressions_topology_and_invalid_domains(self):
        source = node("source", "source")
        cases = [
            {"x": [{"frame": True, "value": .5}]},
            {"x": [{"frame": .5, "value": .5}]},
            {"x": [{"frame": -1, "value": .5}]},
            {"x": [{"frame": 10, "value": .5}]},
            {"x": [{"frame": 1, "value": float("nan")}]},
            {"x": [{"frame": 1, "value": "movie=/etc/passwd"}]},
            {"x": [{"frame": 1, "value": .5, "interpolation": "linear;movie=x"}]},
            {"x": [{"frame": 1, "value": .5}, {"frame": 1, "value": .7}]},
            {"x": []}, {"invert": [{"frame": 1, "value": True}]},
            {"points": [{"frame": 1, "value": [[0, 0], [1, 0], [1, 1], [0, 1]]}]},
            {"points": [{"frame": 1, "value": [[0, 0], [0, 0], [1, 1]]}]},
        ]
        for animation in cases:
            mask = node("mask", "mask", ["source"]); mask["animation"] = animation
            with self.subTest(animation=animation), self.assertRaises(ValueError):
                validate_graph(graph(source, mask), animation_duration=10)
        sharpen = node("sharp", "sharpen", ["source"])
        sharpen["animation"] = {"amount": [{"frame": 0, "value": 1}]}
        with self.assertRaisesRegex(ValueError, "Unsupported animation"):
            validate_graph(graph(source, sharpen))

    def test_animation_budgets_apply_to_disconnected_nodes_and_coordinate_arrays(self):
        source, nodes = node("source", "source"), []
        for index in range(9):
            item = node("blur" + str(index), "blur", ["source"])
            item["animation"] = {"sigma": [{"frame": i, "value": i % 30} for i in range(128)]}
            nodes.append(item)
        with self.assertRaisesRegex(ValueError, "animation budget"):
            validate_graph(graph(source, *nodes, output="source"))
        polygon = [[.5 + .4 * math.cos(i * math.pi / 12), .5 + .4 * math.sin(i * math.pi / 12)] for i in range(24)]
        nodes = []
        for index in range(3):
            item = node("mask" + str(index), "mask", ["source"], points=polygon)
            item["animation"] = {"points": [{"frame": i, "value": polygon} for i in range(64)]}
            nodes.append(item)
        with self.assertRaisesRegex(ValueError, "coordinate values"):
            validate_graph(graph(source, *nodes))

    def test_normalization_preserves_layout_and_does_not_mutate_input(self):
        source = node("source", "source")
        source["position"] = {"x": -122.75, "y": 40}
        raw = graph(source, node("graded", "grade", ["source"], saturation=.4))
        before = copy.deepcopy(raw)
        normalized = validate_graph(raw)
        self.assertEqual(raw, before)
        self.assertEqual(normalized["nodes"][0]["position"], source["position"])
        self.assertEqual(normalized["nodes"][1]["params"]["contrast"], 1)
        self.assertEqual(normalized["nodes"][1]["params"]["saturation"], .4)

    def test_invalid_structure_connections_and_values_fail_before_compile(self):
        good = graph(node("source", "source"), node("grade", "grade", ["source"]))
        cases = []
        for value in (None, [], {"version": 2, "nodes": [], "output": "x"}):
            cases.append(value)
        bad = copy.deepcopy(good); bad["output"] = "missing"; cases.append(bad)
        bad = copy.deepcopy(good); bad["nodes"][1]["inputs"] = ["missing"]; cases.append(bad)
        bad = copy.deepcopy(good); bad["nodes"][1]["inputs"] = ["grade"]; cases.append(bad)
        bad = copy.deepcopy(good); bad["nodes"].append(node("source", "source")); cases.append(bad)
        bad = copy.deepcopy(good); bad["nodes"][1]["params"]["exposure"] = float("nan"); cases.append(bad)
        bad = copy.deepcopy(good); bad["nodes"][1]["params"]["exposure"] = True; cases.append(bad)
        bad = copy.deepcopy(good); bad["nodes"][1]["params"]["filter"] = "movie=/etc/passwd"; cases.append(bad)
        bad = copy.deepcopy(good); bad["nodes"][1]["position"] = {"x": float("inf"), "y": 0}; cases.append(bad)
        bad = copy.deepcopy(good); bad["nodes"].extend([node("a", "blur", ["b"]), node("b", "blur", ["a"])]); cases.append(bad)
        cases.append(graph(node("source", "source"), node("key", "chroma_key", ["source"], color="#00ff00;movie=x")))
        cases.append(graph(node("source", "source"), node("mask", "mask", ["source"], width=0)))
        for raw in cases:
            with self.subTest(raw=repr(raw)[:120]), self.assertRaises(ValueError):
                validate_graph(raw)

    def test_node_and_working_image_limits(self):
        raw = graph(node("source", "source"), *[node("n" + str(i), "blur", ["source"]) for i in range(32)])
        with self.assertRaisesRegex(ValueError, "1–32"):
            validate_graph(raw)
        chain = [node("source", "source")]
        for i in range(12):
            chain.append(node("n" + str(i), "blur", [chain[-1]["id"]]))
        with self.assertRaisesRegex(ValueError, "working-image budget"):
            validate_graph(graph(*chain), 8192, 4096)

    def test_curve_polygon_and_blend_parameters_are_bounded_data(self):
        source = node("source", "source")
        invalid = [
            node("curve", "curves", ["source"], master="0/0;movie=/tmp/input"),
            node("curve", "curves", ["source"], master=[[0, 0], [.5, .2], [.5, .8], [1, 1]]),
            node("curve", "curves", ["source"], red=[[.1, 0], [1, 1]]),
            node("curve", "curves", ["source"], blue=[[0, 0], [1, float("nan")]]),
            node("curve", "curves", ["source"], green=[[i / 12, i / 12] for i in range(13)]),
            node("mask", "mask", ["source"], shape="polygon", points=[[0, 0], [1, 1]]),
            node("mask", "mask", ["source"], shape="polygon", points=[[0, 0], [True, 1], [1, 0]]),
            node("mask", "mask", ["source"], shape="polygon", points=[[0, 0], [0, 0], [1, 1]]),
            node("mask", "mask", ["source"], rotation=float("inf")),
            node("merge", "merge", ["source", "source"], mode="multiply;movie=x"),
        ]
        for item in invalid:
            with self.subTest(node=item), self.assertRaises(ValueError):
                validate_graph(graph(source, item))
        raw = graph(source, node("curve", "curves", ["source"], red=[[0, 1], [1, 0]]))
        normalized = validate_graph(raw)
        self.assertEqual(normalized["nodes"][1]["params"]["master"], [[0, 0], [1, 1]])
        normalized["nodes"][1]["params"]["red"][0][1] = .5
        self.assertEqual(raw["nodes"][1]["params"]["red"][0][1], 1)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and ffprobe are required")
class CompositorMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-NODE-TEST-")
        cls.root = Path(cls.temporary.name)
        (cls.root / "media").mkdir()

        def png(name, pixel):
            def chunk(kind, content):
                return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff)
            data = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(160)) for y in range(90))
            content = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 160, 90, 8, 6, 0, 0, 0))
            content += chunk(b"IDAT", zlib.compress(data)) + chunk(b"IEND", b"")
            (cls.root / "media" / (name + ".png")).write_bytes(content)

        png("ENGINE_TEST_gray", lambda x, y: (80, 80, 80, 255))
        png("ENGINE_TEST_red", lambda x, y: (255, 0, 0, 255))
        png("ENGINE_TEST_blue", lambda x, y: (0, 0, 255, 255))
        png("ENGINE_TEST_key", lambda x, y: (0, 255, 0, 255) if x < 80 else (0, 0, 255, 128))
        png("ENGINE_TEST_stripes", lambda x, y: (64, 64, 64, 255) if (x // 8) % 2 == 0 else (128, 128, 128, 255))
        png("ENGINE_TEST_alpha", lambda x, y: (20, 60, 120, 128))
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-filter_complex_threads", "1",
                        "-f", "lavfi", "-i", "color=red:s=160x90:r=12:d=1", "-f", "lavfi", "-i", "color=blue:s=160x90:r=12:d=1",
                        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-c:v", "ffv1", "-threads", "1",
                        str(cls.root / "media" / "ENGINE_TEST_switch.mkv")], check=True, capture_output=True, timeout=30)
        with wave.open(str(cls.root / "media" / "ENGINE_TEST_audio.wav"), "wb") as target:
            target.setparams((1, 2, 48000, 48000, "NONE", "not compressed"))
            target.writeframes(b"\0\0" * 48000)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def project(self, *names):
        assets = []
        for name in names:
            suffix = ".mkv" if name == "switch" else ".wav" if name == "audio" else ".png"
            path = "media/ENGINE_TEST_" + name + suffix
            assets.append({"id": name, "path": path, "name": "ENGINE TEST ONLY", **probe_media(self.root / path)})
        return {"version": 1, "id": "nodes_test", "name": "ENGINE TEST ONLY", "fps": 12, "width": 160, "height": 90,
                "assets": assets, "clips": [], "titles": []}

    def clip(self, asset, compositor=None, **options):
        item = {"id": asset + "clip", "asset_id": asset, "track": 0, "start": 0, "in": 0, "duration": 12, **options}
        if compositor is not None:
            item["compositor"] = compositor
        return item

    def render(self, project, name):
        output = self.root / ("ENGINE_TEST_" + name + ".mp4")
        report = render_project(project, self.root, output, "h264")
        self.assertEqual(report["frames"], 12)
        return output

    def pixel(self, path, x=80, y=45):
        result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-threads", "1", "-ss", "0.5", "-i", str(path),
                                 "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-threads", "1", "pipe:1"],
                                check=True, capture_output=True, timeout=20)
        at = (y * 160 + x) * 3
        return tuple(result.stdout[at:at + 3])

    def graph_rgba(self, name, recipe):
        """Decode the real graph's lossless RGBA result, including its matte."""
        clauses, output = compile_graph(recipe, "sourceimage", "check")
        filters = "[0:v]format=rgba[sourceimage];" + ";".join(clauses)
        result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-threads", "1", "-filter_complex_threads", "1",
                                 "-i", str(self.root / "media" / ("ENGINE_TEST_" + name + ".png")),
                                 "-filter_complex", filters, "-map", "[" + output + "]", "-frames:v", "1",
                                 "-threads", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1"],
                                check=True, capture_output=True, timeout=20)
        self.assertEqual(len(result.stdout), 160 * 90 * 4)
        return lambda x=80, y=45: tuple(result.stdout[(y * 160 + x) * 4:(y * 160 + x) * 4 + 4])

    def graph_frames(self, name, recipe, count=9, **timing):
        clauses, output = compile_graph(recipe, "sourceimage", "animationcheck", **timing)
        filters = "[0:v]format=rgba[sourceimage];" + ";".join(clauses)
        result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-threads", "1", "-filter_complex_threads", "1",
                                 "-loop", "1", "-framerate", "12", "-i", str(self.root / "media" / ("ENGINE_TEST_" + name + ".png")),
                                 "-filter_complex", filters, "-map", "[" + output + "]", "-frames:v", str(count),
                                 "-threads", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1"],
                                check=True, capture_output=True, timeout=30)
        size = 160 * 90 * 4
        self.assertEqual(len(result.stdout), size * count)
        return [result.stdout[at:at + size] for at in range(0, len(result.stdout), size)]

    def frozen_graph(self, recipe, frame, **domain):
        frozen = validate_graph(recipe, **domain)
        for item in frozen["nodes"]:
            item["params"] = node_params_at(item, frame)
            item.pop("animation", None)
        return frozen

    def test_animated_polygon_deformation_transform_and_feather_match_evaluated_frames(self):
        mask = node("mask", "mask", ["source"], shape="polygon", x=.25, width=.45, height=.7,
                    points=[[0, 1], [.5, 0], [1, 1]])
        mask["animation"] = {
            "x": [{"frame": 0, "value": .25, "interpolation": "ease_in_out"}, {"frame": 8, "value": .75}],
            "rotation": [{"frame": 0, "value": -30}, {"frame": 8, "value": 40}],
            "feather": [{"frame": 2, "value": 0}, {"frame": 6, "value": .3}],
            "points": [{"frame": 0, "value": [[0, 1], [.5, 0], [1, 1]]},
                       {"frame": 8, "value": [[.2, .8], [.7, .1], [.9, 1]]}],
        }
        recipe = graph(node("source", "source"), mask)
        frames = self.graph_frames("alpha", recipe)
        self.assertNotEqual(frames[0], frames[-1])
        for frame in (0, 2, 4, 8):
            expected = self.graph_frames("alpha", self.frozen_graph(recipe, frame), 1)[0]
            differences = [abs(a - b) for a, b in zip(frames[frame], expected)]
            self.assertLessEqual(max(differences), 1, f"polygon frame {frame}")
            self.assertEqual(frames[frame][:3], bytes((20, 60, 120)))
            self.assertLessEqual(max(frames[frame][3::4]), 128)

    def test_runtime_animated_grade_blur_and_chroma_match_static_evaluations(self):
        grade = node("grade", "grade", ["source"], contrast=.9, saturation=.7, temperature=-.2)
        grade["animation"] = {
            "exposure": [{"frame": 0, "value": 0, "interpolation": "constant"}, {"frame": 4, "value": 1}],
            "contrast": [{"frame": 2, "value": .8}, {"frame": 8, "value": 1.3}],
            "saturation": [{"frame": 0, "value": .7, "interpolation": "ease_out"}, {"frame": 8, "value": 1.2}],
            "temperature": [{"frame": 0, "value": -.2}, {"frame": 6, "value": .3}],
        }
        blur = node("blur", "blur", ["source"], sigma=0)
        blur["animation"] = {"sigma": [{"frame": 0, "value": 0}, {"frame": 8, "value": 5}]}
        key = node("key", "chroma_key", ["source"], color="#00ff00", blend=.1)
        key["animation"] = {"similarity": [{"frame": 0, "value": .1}, {"frame": 8, "value": .8}]}
        for source, item in (("alpha", grade), ("stripes", blur), ("gray", key)):
            with self.subTest(kind=item["type"]):
                recipe = graph(node("source", "source"), item)
                frames = self.graph_frames(source, recipe)
                self.assertNotEqual(frames[0], frames[-1])
                for frame in (0, 2, 4, 8):
                    expected = self.graph_frames(source, self.frozen_graph(recipe, frame), 1)[0]
                    self.assertLessEqual(max(abs(a - b) for a, b in zip(frames[frame], expected)), 2)
                if source == "alpha":
                    self.assertEqual(set(frames[0][3::4]), {128})
                    self.assertEqual(set(frames[8][3::4]), {128})

    def test_animated_merge_opacity_retains_alpha_in_every_blend_mode(self):
        for mode in ("normal", "multiply", "screen", "add", "difference"):
            with self.subTest(mode=mode):
                merge = node("merge", "merge", ["source", "source"], mode=mode, opacity=0)
                merge["animation"] = {"opacity": [{"frame": 0, "value": 0}, {"frame": 8, "value": 1}]}
                recipe = graph(node("source", "source"), merge)
                frames = self.graph_frames("alpha", recipe)
                self.assertEqual(frames[0][3], 128)
                self.assertAlmostEqual(frames[-1][3], 192, delta=1)
                for frame in (0, 4, 8):
                    expected = self.graph_frames("alpha", self.frozen_graph(recipe, frame), 1)[0]
                    self.assertLessEqual(max(abs(a - b) for a, b in zip(frames[frame], expected)), 1)

    def test_trimmed_animation_offsets_replay_identical_decoded_pixels(self):
        grade = node("grade", "grade", ["source"])
        grade["animation"] = {"exposure": [{"frame": -4, "value": -.5, "interpolation": "ease_in_out"},
                                           {"frame": 0, "value": 0, "interpolation": "ease_out"},
                                           {"frame": 15, "value": 1}]}
        mask = node("mask", "mask", ["grade"], shape="ellipse", width=.5, height=.6)
        mask["animation"] = {"x": [{"frame": 0, "value": .2, "interpolation": "ease_in_out"},
                                   {"frame": 15, "value": .8}]}
        recipe = graph(node("source", "source"), grade, mask)
        domain = {"animation_start": -4, "animation_duration": 16}
        full = self.graph_frames("alpha", recipe, 16, **domain)
        right = self.graph_frames("alpha", recipe, 9, frame_offset=7, **domain)
        self.assertEqual(right, full[7:])
        negative = self.graph_frames("alpha", recipe, 3, frame_offset=-4, **domain)
        for index, data in enumerate(negative):
            expected = self.graph_frames("alpha", self.frozen_graph(recipe, index - 4, **domain), 1)[0]
            self.assertLessEqual(max(abs(a - b) for a, b in zip(data, expected)), 1)

    def test_maximum_scalar_key_count_compiles_without_linear_parser_depth(self):
        grade = node("grade", "grade", ["source"])
        grade["animation"] = {"exposure": [{"frame": frame, "value": .5 if frame % 2 else 0,
                                            "interpolation": "ease_in_out"} for frame in range(128)]}
        recipe = graph(node("source", "source"), grade)
        frame = self.graph_frames("gray", recipe, 1, frame_offset=127, animation_duration=128)[0]
        expected = self.graph_frames("gray", self.frozen_graph(recipe, 127), 1)[0]
        self.assertEqual(frame, expected)

    def test_timeline_preview_and_movie_preserve_node_motion_across_split(self):
        grade = node("grade", "grade", ["source"])
        grade["animation"] = {"exposure": [{"frame": 0, "value": 0, "interpolation": "ease_out"},
                                           {"frame": 11, "value": 1}]}
        mask = node("mask", "mask", ["grade"], shape="ellipse", x=.25, width=.4, height=.7, feather=.1)
        mask["animation"] = {"x": [{"frame": 0, "value": .25, "interpolation": "ease_in_out"},
                                   {"frame": 11, "value": .75}]}
        project = self.project("gray")
        original = self.clip("gray", graph(node("source", "source"), grade, mask), animation_duration=12)
        project["clips"] = [original]
        before, after = self.root / "preview_before_split.png", self.root / "preview_after_split.png"
        render_frame(project, self.root, 7, before)
        left, right = copy.deepcopy(original), copy.deepcopy(original)
        left["duration"] = 4
        right.update(id="right", start=4, duration=8, animation_offset=4)
        project["clips"] = [left, right]
        render_frame(project, self.root, 7, after)
        movie = self.render(project, "node_animation_split")

        def decode(path, frames=1):
            result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-threads", "1", "-i", str(path),
                                     "-frames:v", str(frames), "-threads", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                                    check=True, capture_output=True, timeout=20)
            return result.stdout

        a, b, pixels = decode(before), decode(after), decode(movie, 12)
        self.assertEqual(a, b)
        size = 160 * 90 * 3
        frame = pixels[7 * size:8 * size]
        self.assertEqual(len(a), len(frame))
        self.assertLess(sum(abs(x - y) for x, y in zip(a, frame)) / size, 3)

    def test_master_and_rgb_curves_change_real_pixels_without_changing_alpha(self):
        recipe = graph(node("source", "source"), node("curve", "curves", ["source"],
                       red=[[0, 1], [1, 0]], master=[[0, 0], [1, .5]]))
        pixel = self.graph_rgba("alpha", recipe)()
        for actual, expected in zip(pixel, (117, 30, 60, 128)):
            self.assertAlmostEqual(actual, expected, delta=2)
        p = self.project("gray")
        p["clips"] = [self.clip("gray", graph(node("source", "source"), node("curve", "curves", ["source"],
                      master=[[0, 0], [.3, .8], [1, 1]])))]
        rendered = self.render(p, "curve_midpoint")
        self.assertGreater(min(self.pixel(rendered)), 195)

    def test_rotating_mask_turns_its_geometry_in_pixel_space(self):
        recipe = graph(node("source", "source"), node("mask", "mask", ["source"], width=.75, height=.25))
        p = self.project("red", "blue")
        p["clips"] = [self.clip("red"), self.clip("blue", recipe, track=1)]
        horizontal = self.render(p, "horizontal_mask")
        self.assertGreater(self.pixel(horizontal, 110, 45)[2], 240)
        self.assertGreater(self.pixel(horizontal, 80, 10)[0], 240)
        p["clips"][1]["compositor"]["nodes"][1]["params"]["rotation"] = 90
        vertical = self.render(p, "vertical_mask")
        self.assertGreater(self.pixel(vertical, 110, 45)[0], 240)
        self.assertGreater(self.pixel(vertical, 80, 10)[2], 240)

    def test_polygon_vertices_feather_and_inversion_control_exported_matte(self):
        recipe = graph(node("source", "source"), node("mask", "mask", ["source"],
                       shape="polygon", points=[[0, 1], [.5, 0], [1, 1]], feather=.2))
        pixels = self.graph_rgba("alpha", recipe)
        self.assertEqual(pixels(80, 45)[3], 128)
        self.assertEqual(pixels(10, 10)[3], 0)
        self.assertTrue(10 < pixels(43, 45)[3] < 90)
        p = self.project("red", "blue")
        p["clips"] = [self.clip("red"), self.clip("blue", recipe, track=1)]
        original = self.render(p, "polygon_original")
        self.assertGreater(self.pixel(original, 40, 70)[2], 210)
        mask = p["clips"][1]["compositor"]["nodes"][1]["params"]
        mask["points"][0] = [.4, 1]
        moved = self.render(p, "polygon_moved_vertex")
        self.assertGreater(self.pixel(moved, 40, 70)[0], 235)
        mask["invert"] = True
        inverse = self.render(p, "polygon_inverse")
        self.assertGreater(self.pixel(inverse, 40, 70)[2], 235)
        self.assertGreater(self.pixel(inverse, 96, 45)[0], 235)

    def test_separable_blend_modes_preserve_partial_alpha_and_source_over_math(self):
        color, ab, opacity = (20, 60, 120), 128 / 255, .5
        af = ab * opacity
        output_alpha = af + ab * (1 - af)
        operations = {"multiply": lambda a, b: a * b / 255,
                      "screen": lambda a, b: 255 - (255 - a) * (255 - b) / 255,
                      "add": lambda a, b: min(255, a + b),
                      "difference": lambda a, b: abs(a - b)}
        for mode, blend in operations.items():
            with self.subTest(mode=mode):
                recipe = graph(node("source", "source"), node("mix", "merge", ["source", "source"], mode=mode, opacity=opacity))
                actual = self.graph_rgba("alpha", recipe)()
                expected = [(af * ((1 - ab) * c + ab * blend(c, c)) + ab * (1 - af) * c) / output_alpha for c in color]
                for value, reference in zip(actual, expected + [output_alpha * 255]):
                    self.assertAlmostEqual(value, reference, delta=3)
                # A fully transparent background must not darken the source,
                # even in multiply mode. A transparent foreground is neutral.
                for inputs in (["empty", "source"], ["source", "empty"]):
                    empty = node("empty", "mask", ["source"], width=.1, height=.1)
                    recipe = graph(node("source", "source"), empty, node("mix", "merge", inputs, mode=mode))
                    actual = self.graph_rgba("alpha", recipe)(10, 10)
                    for value, reference in zip(actual, color + (128,)):
                        self.assertAlmostEqual(value, reference, delta=2)

    def test_branching_merge_opacity_and_selected_output_change_exported_pixels(self):
        recipe = graph(node("source", "source"), node("dark", "grade", ["source"], exposure=-1),
                       node("light", "grade", ["source"], exposure=1),
                       node("region", "mask", ["light"], x=.75, width=.5),
                       node("mix", "merge", ["dark", "region"], opacity=.5))
        p = self.project("gray"); p["clips"] = [self.clip("gray", recipe)]
        output = self.render(p, "branch_merge")
        outside, inside = self.pixel(output, 20)[0], self.pixel(output, 120)[0]
        self.assertLess(outside, 60)
        self.assertGreater(inside, outside + 40)
        self.assertLess(inside, 135, "Merge opacity must blend the bright branch, not replace the background")
        p["clips"][0]["compositor"]["output"] = "dark"
        alternate = self.render(p, "selected_output")
        self.assertLess(self.pixel(alternate, 120)[0], inside - 40)
        # Connecting both merge ports to one node requires two real stream uses.
        p["clips"][0]["compositor"] = graph(node("source", "source"), node("same", "merge", ["source", "source"]))
        repeated = self.render(p, "repeated_port")
        self.assertTrue(70 < self.pixel(repeated)[0] < 90)

    def test_ellipse_feather_and_inversion_preserve_underlying_layer(self):
        recipe = graph(node("source", "source"), node("matte", "mask", ["source"], shape="ellipse", width=.7, height=.8, feather=.5))
        p = self.project("red", "blue")
        p["clips"] = [self.clip("red"), self.clip("blue", recipe, track=1)]
        output = self.render(p, "feather")
        self.assertGreater(self.pixel(output)[2], 210)
        self.assertGreater(self.pixel(output, 10, 5)[0], 210)
        edge = self.pixel(output, 124, 45)
        self.assertGreater(edge[0], 65); self.assertGreater(edge[2], 65)
        p["clips"][1]["compositor"]["nodes"][1]["params"]["invert"] = True
        inverse = self.render(p, "inverse")
        self.assertGreater(self.pixel(inverse)[0], 210)
        self.assertGreater(self.pixel(inverse, 10, 5)[2], 210)

    def test_chroma_key_multiplies_existing_source_alpha(self):
        p = self.project("red", "key")
        recipe = graph(node("source", "source"), node("key", "chroma_key", ["source"]))
        p["clips"] = [self.clip("red"), self.clip("key", recipe, track=1)]
        output = self.render(p, "key_alpha")
        left, right = self.pixel(output, 20), self.pixel(output, 120)
        self.assertGreater(left[0], 210); self.assertLess(left[1], 30)
        self.assertGreater(right[0], 80, "Keying must retain the source's partial alpha")
        self.assertGreater(right[2], 80)

    def test_merge_preserves_accumulated_alpha_for_timeline_composition(self):
        p = self.project("red", "alpha")
        recipe = graph(node("source", "source"), node("mix", "merge", ["source", "source"], opacity=.5))
        p["clips"] = [self.clip("red"), self.clip("alpha", recipe, track=1)]
        output = self.render(p, "merge_alpha")
        red, green, blue = self.pixel(output)
        # Two half-alpha images, with foreground opacity .5, produce .625
        # coverage. Their RGB must remain straight, then composite onto red.
        self.assertTrue(85 < red < 130)
        self.assertTrue(20 < green < 55)
        self.assertTrue(55 < blue < 95)

    def test_color_filters_keep_alpha_and_blur_sharpen_change_edges(self):
        p = self.project("red", "alpha")
        recipe = graph(node("source", "source"), node("grade", "grade", ["source"], exposure=.5, saturation=.7),
                       node("blur", "blur", ["grade"], sigma=2), node("sharp", "sharpen", ["blur"], amount=1))
        p["clips"] = [self.clip("red"), self.clip("alpha", recipe, track=1)]
        output = self.render(p, "color_alpha")
        sample = self.pixel(output)
        self.assertGreater(sample[0], 100); self.assertGreater(sample[2], 40)
        p = self.project("stripes")
        p["clips"] = [self.clip("stripes")]
        plain = self.render(p, "plain_stripes")
        p["clips"][0]["compositor"] = graph(node("source", "source"), node("blur", "blur", ["source"], sigma=3))
        blurred = self.render(p, "blur_stripes")
        self.assertGreater(self.pixel(blurred, 7)[0], self.pixel(plain, 7)[0] + 15)
        p["clips"][0]["compositor"] = graph(node("source", "source"), node("sharp", "sharpen", ["source"], amount=2))
        sharpened = self.render(p, "sharp_stripes")
        self.assertLess(self.pixel(sharpened, 7)[0], self.pixel(plain, 7)[0] - 10)

    def test_video_trim_precedes_graph_and_audio_graphs_are_rejected(self):
        p = self.project("switch")
        recipe = graph(node("source", "source"), node("gray", "grade", ["source"], saturation=0))
        p["clips"] = [self.clip("switch", recipe)]
        p["clips"][0]["in"] = 12
        output = self.render(p, "trim")
        sample = self.pixel(output)
        self.assertLess(max(sample), 50, "Trim should select the darker-luma blue half before the graph")
        self.assertLess(max(sample) - min(sample), 8)
        p = self.project("audio"); p["clips"] = [self.clip("audio", graph(node("source", "source")), track=-1)]
        with self.assertRaisesRegex(ValueError, "picture clips"):
            validate_project(p, self.root)


if __name__ == "__main__":
    unittest.main()
