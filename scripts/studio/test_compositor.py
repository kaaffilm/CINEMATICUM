"""Decoded media checks for editable node graphs. Fixtures are not film footage."""
import copy
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
import zlib

from compositor import validate_graph
from engine import probe_media, render_project, validate_project


def node(ident, kind, inputs=(), **params):
    return {"id": ident, "type": kind, "inputs": list(inputs), "params": params}


def graph(*nodes, output=None):
    return {"version": 1, "nodes": list(nodes), "output": output or nodes[-1]["id"]}


class GraphValidationTests(unittest.TestCase):
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
