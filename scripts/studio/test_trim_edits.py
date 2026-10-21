"""Editorial edits checked against timing invariants and decoded source frames."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from engine import _graph, probe_media, validate_project


def evaluate(project, kind, delta, clip_id="middle"):
    program = r"""
const fs=require('fs'),vm=require('vm'),request=JSON.parse(fs.readFileSync(0,'utf8'));
const context={window:{}};vm.createContext(context);
vm.runInContext(fs.readFileSync(request.script,'utf8'),context);
try {const result=context.window.CinematicumEditing.trimEdit(request.project,request.clip,request.kind,request.delta);
const changed=new Map(result.clips.map(c=>[c.id,c]));
request.project.clips=request.project.clips.map(c=>changed.get(c.id)||c);
process.stdout.write(JSON.stringify({result,project:request.project}));}
catch(error){process.stdout.write(JSON.stringify({error:error.message}));}
"""
    response = subprocess.run([shutil.which("node"), "-e", program], input=json.dumps({
        "script": str(Path(__file__).parent / "web/editing.js"), "project": project,
        "clip": clip_id, "kind": kind, "delta": delta}), text=True, capture_output=True, timeout=10)
    if response.returncode:
        raise AssertionError(response.stderr)
    result = json.loads(response.stdout)
    if "error" in result:
        raise ValueError(result["error"])
    return result


def timeline():
    clips = [{"id": name, "asset_id": "source", "start": index * 8, "duration": 8,
              "in": 8 + index * 16, "track": 0, "speed": 1, "reverse": False,
              "animation_start": 0, "animation_duration": 8, "animation_offset": 0,
              "keyframes": [{"frame": 0, "x": -.1}, {"frame": 7, "x": .1}],
              "audio": {"fade_in": 2, "fade_out": 1, "fade_duration": 8, "fade_offset": 0}}
             for index, name in enumerate(("before", "middle", "after"))]
    return {"version": 1, "id": "trim-proof", "name": "ENGINE TEST trim proof", "fps": 24,
            "width": 32, "height": 24, "clips": clips, "titles": [], "tracks": [],
            "assets": [{"id": "source", "kind": "video", "duration": 80 / 24}]}


@unittest.skipUnless(shutil.which("node"), "Node is required to evaluate the shipped editor")
class TrimEditTests(unittest.TestCase):
    def test_slip_retains_timeline_animation_and_fractional_reverse_clock(self):
        for reverse in (False, True):
            for speed in (.25, .5, 1, 1.5, 4):
                p = timeline()
                c = p["clips"][1]
                c.update(speed=speed, reverse=reverse)
                old = copy.deepcopy(p)
                r = evaluate(p, "slip", 3)
                edited = r["project"]["clips"][1]
                self.assertEqual(edited["in"], 24 + 3 * speed * (-1 if reverse else 1))
                for key in set(c) - {"in"}:
                    self.assertEqual(edited[key], c[key], key)
                self.assertEqual(p, old)
                # A positive slip advances along playback direction, including
                # a reverse clip, without rounding fractional source positions.
                for frame in range(c["duration"]):
                    source = lambda clip, f: clip["in"] + ((clip["duration"] - 1 - f) if reverse else f) * speed
                    self.assertAlmostEqual(source(edited, frame), source(c, frame + 3))

    def test_slide_keeps_selected_source_and_fixed_sequence_endpoints(self):
        p = timeline()
        r = evaluate(p, "slide", 3)
        a, b, c = r["project"]["clips"]
        self.assertEqual([(x["start"], x["duration"], x["in"]) for x in (a, b, c)],
                         [(0, 11, 8), (11, 8, 24), (19, 5, 43)])
        self.assertEqual(a["start"], p["clips"][0]["start"])
        self.assertEqual(c["start"] + c["duration"], 24)
        for key in set(b) - {"start"}:
            self.assertEqual(b[key], p["clips"][1][key], key)
        self.assertEqual(c["animation_offset"], 3)
        self.assertEqual(c["audio"]["fade_offset"], 3)
        self.assertEqual(c["keyframes"], p["clips"][2]["keyframes"])

    def test_roll_moves_one_cut_only_and_preserves_continuous_animation_domains(self):
        p = timeline()
        r = evaluate(p, "roll", -3)
        a, b, c = r["project"]["clips"]
        self.assertEqual(a, p["clips"][0])
        self.assertEqual((b["start"], b["duration"], b["in"]), (8, 5, 24))
        self.assertEqual((c["start"], c["duration"], c["in"]), (13, 11, 37))
        self.assertEqual(c["animation_offset"], -3)
        self.assertEqual(c["animation_start"], -3)
        self.assertEqual(c["animation_duration"], 8)
        self.assertEqual(c["audio"]["fade_offset"], -3)
        self.assertEqual(c["audio"]["fade_duration"], 8)
        self.assertEqual(c["keyframes"], p["clips"][2]["keyframes"])

    def test_handles_clamp_and_one_frame_neighbors_survive(self):
        p = timeline()
        self.assertEqual(evaluate(p, "slide", 999)["result"]["delta"], 7)
        self.assertEqual(evaluate(p, "slide", -999)["result"]["delta"], -7)
        self.assertEqual(evaluate(p, "roll", 999)["project"]["clips"][2]["duration"], 1)
        for reverse in (False, True):
            p["clips"][1].update(reverse=reverse)
            for requested in (-1000, 1000):
                r = evaluate(p, "slip", requested)
                c = r["project"]["clips"][1]
                self.assertGreaterEqual(c["in"], 0)
                self.assertLessEqual(c["in"] + c["duration"] * c["speed"], 80)
                self.assertTrue(r["result"]["limited"])

    def test_adjacent_reverse_and_retimed_handles_use_correct_end(self):
        p = timeline()
        for c in p["clips"]:
            c.update(reverse=True, speed=1.5)
        r = evaluate(p, "slide", 2)
        a, b, c = r["project"]["clips"]
        self.assertEqual(a["in"], 5)
        self.assertEqual(b["in"], 24)
        self.assertEqual(c["in"], 40)
        self.assertEqual((a["duration"], b["start"], c["duration"]), (10, 10, 6))

    def test_locked_ambiguous_gapped_and_noninteger_edits_reject(self):
        for modify, kind, phrase in (
            (lambda p: p.update(tracks=[{"id": 0, "locked": True}]), "slip", "Unlock"),
            (lambda p: p["clips"][2].update(start=17), "roll", "touching"),
            (lambda p: p["clips"][0].update(duration=7), "slide", "touching"),
            (lambda p: p["clips"].append({**p["clips"][0], "id": "overlap", "start": 4, "duration": 8}), "slide", "unoverlapped"),
            (lambda p: p["assets"][0].update(kind="image"), "slip", "still image"),
        ):
            p = timeline(); modify(p)
            with self.assertRaisesRegex(ValueError, phrase):
                evaluate(p, kind, 1)
        with self.assertRaisesRegex(ValueError, "whole number"):
            evaluate(timeline(), "slip", .5)


@unittest.skipUnless(shutil.which("node") and shutil.which("ffmpeg") and shutil.which("ffprobe"), "Node and FFmpeg are required")
class DecodedTrimTests(unittest.TestCase):
    def test_actual_render_frames_match_slip_slide_roll_source_selection(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-trim-ENGINE-TEST-") as temp:
            root = Path(temp); (root / "media").mkdir()
            source = root / "media/source.mkv"
            pixels = b"".join(bytes([10 + 2 * f, 32, 90]) * (32 * 24) for f in range(80))
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", "32x24", "-r", "24", "-i", "pipe:0", "-c:v", "ffv1", "-threads", "1", str(source)],
                           input=pixels, check=True, capture_output=True, timeout=15)
            p = timeline()
            p["assets"] = [{**probe_media(source), "id": "source", "path": "media/source.mkv", "name": "ENGINE TEST frame ramp"}]
            for c in p["clips"]:
                c["keyframes"] = []
            expected = {
                ("slip", 3): list(range(8, 16)) + list(range(27, 35)) + list(range(40, 48)),
                ("slide", 2): list(range(8, 18)) + list(range(24, 32)) + list(range(42, 48)),
                ("roll", -2): list(range(8, 16)) + list(range(24, 30)) + list(range(38, 48)),
            }
            for (kind, delta), frames in expected.items():
                edited = validate_project(evaluate(p, kind, delta)["project"], root)
                inputs, graph, count = _graph(edited, root, root)
                self.assertEqual(count, 24)
                command = [shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-filter_complex_threads", "1"] + inputs + [
                    "-filter_complex", graph, "-map", "[aout]", "-f", "null", "-", "-map", "[vout]", "-frames:v", "24",
                    "-threads", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
                data = subprocess.run(command, check=True, capture_output=True, timeout=15).stdout
                self.assertEqual(len(data), 24 * 32 * 24 * 3)
                for n, frame in enumerate(frames):
                    sample = data[(n * 32 * 24 + 16 + 12 * 32) * 3:][:3]
                    self.assertLessEqual(max(abs(a - b) for a, b in zip(sample, (10 + 2 * frame, 32, 90))), 3, (kind, n, sample, frame))


if __name__ == "__main__":
    unittest.main()
