"""Production assembly gates with real decoded ENGINE TEST media, not film shots."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from engine import render_project, validate_project
from production import normalize_plan, review_plan, prepare_plan, conform_plan, export_plan


class PlanSchemaTests(unittest.TestCase):
    def plan(self):
        return {"film": "ENGINE TEST plan", "fps": 24, "width": 32, "height": 24,
                "shots": [{"id": "one", "filename": "one.mp4", "duration": 1},
                          {"id": "two", "filename": "two.mp4", "duration": 2}],
                "runtime_target_seconds": 3, "required_source_dir": "/never/open/this"}

    def test_repository_shotlist_is_a_complete_18_shot_107_second_plan(self):
        path = Path(__file__).resolve().parents[2] / "production/THE_LAST_RENDER/shots/shotlist.json"
        if not path.is_file():
            self.skipTest("Production repository fixture is not bundled in this runtime")
        result = normalize_plan(path.read_text())
        self.assertEqual((len(result["shots"]), result["runtime_frames"]), (18, 107 * 24))
        self.assertEqual((result["width"], result["height"]), (1920, 1080))
        self.assertEqual(result["shots"][-1]["start_frame"] + result["shots"][-1]["duration_frames"], 2568)

    def test_canonical_plan_roundtrip_exact_rational_clock_and_no_paths_opened(self):
        original = self.plan()
        with patch("builtins.open", side_effect=AssertionError("Plan parsing must not open source hints")):
            plan = normalize_plan(original)
        self.assertEqual(normalize_plan(plan), plan)
        self.assertEqual(plan["shots"][1]["start_frame"], 24)
        rational = self.plan()
        rational.update(fps=23.976, frame_rate={"numerator": 24000, "denominator": 1001}, runtime_frames=72)
        rational.pop("runtime_target_seconds")
        for shot, frames in zip(rational["shots"], (24, 48)):
            shot.pop("duration")
            shot["duration_frames"] = frames
        result = normalize_plan(rational)
        self.assertEqual(result["frame_rate"], {"numerator": 24000, "denominator": 1001})
        self.assertEqual(result["runtime_frames"], 72)

    def test_duplicate_ids_names_members_and_malformed_schema_reject(self):
        for change in ({"id": "one"}, {"filename": "one.mp4"}, {"filename": "../two.mp4"},
                       {"filename": "https://example.test/two.mp4"}, {"filename": "two.png"},
                       {"duration": True}, {"duration": -1}, {"unexpected": 1}):
            plan = self.plan()
            plan["shots"][1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_plan(plan)
        for change in ({"runtime_target_seconds": 2}, {"runtime_frames": 3}, {"width": 33},
                       {"fps": 23.976}, {"shots": []}, {"version": True},
                       {"toy_renderer_allowed": True}, {"fake_fallback_allowed": 0}):
            plan = self.plan()
            plan.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_plan(plan)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            normalize_plan('{"film":"A","film":"B"}')
        with self.assertRaises(ValueError):
            normalize_plan('{"film":"A","fps":NaN}')

    def test_off_grid_conflicting_durations_and_wrong_start_reject_without_rounding(self):
        for change in ({"duration": .01}, {"duration_frames": 23}, {"start_frame": 10}):
            plan = self.plan()
            plan["shots"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_plan(plan)
        precise = self.plan()
        precise["shots"][0]["duration"] = 1 / 24
        precise.pop("runtime_target_seconds")
        self.assertEqual(normalize_plan(precise)["shots"][0]["duration_frames"], 1)

    def test_extreme_numeric_inputs_are_bounded_value_errors_not_overflows(self):
        huge = 10 ** 1000
        for key in ("fps", "runtime_target_seconds", "runtime_frames", "width", "height"):
            plan = self.plan()
            plan[key] = huge
            with self.subTest(key=key), self.assertRaises(ValueError):
                normalize_plan(json.dumps(plan))
        for key in ("duration", "duration_seconds", "duration_frames", "start_frame"):
            plan = self.plan()
            plan["shots"][0][key] = huge
            with self.subTest(key=key), self.assertRaises(ValueError):
                normalize_plan(json.dumps(plan))
        for raw in ('{"film":"A","fps":1e309}',
                    json.dumps(self.plan()).replace('"duration": 1', '"duration": 1e309')):
            with self.subTest(raw=raw[:70]), self.assertRaises(ValueError):
                normalize_plan(raw)

    def test_plan_size_structure_and_integer_frame_boundaries_reject(self):
        for raw in (' ' * (2 * 1024 * 1024) + '{}', '[' * 14 + '0' + ']' * 14):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                normalize_plan(raw)
        for key in ("duration_frames", "start_frame"):
            for value in (True, 1.5, "1", None, [], {}):
                plan = self.plan()
                plan["shots"][0][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    normalize_plan(plan)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Real FFmpeg media is required")
class ProductionMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="cinematicum-ENGINE-TEST-production-")
        cls.root = Path(cls.temp.name)
        (cls.root / "media").mkdir()
        for name, color, frequency in (("a", "red", 440), ("b", "blue", 880)):
            cls.ffmpeg(["-f", "lavfi", "-i", f"color=c={color}:s=32x24:r=12:d=1",
                        "-f", "lavfi", "-i", f"sine=f={frequency}:r=48000:d=1",
                        "-c:v", "ffv1", "-c:a", "pcm_s16le", str(cls.root / f"media/{name}.mkv")])
        cls.ffmpeg(["-i", str(cls.root / "media/a.mkv"), "-frames:v", "1", "-threads", "1", str(cls.root / "media/still.png")])
        cls.ffmpeg(["-i", str(cls.root / "media/a.mkv"), "-vn", "-c:a", "pcm_s16le", str(cls.root / "media/sound.wav")])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def ffmpeg(arguments):
        return subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1", "-threads", "1"] + arguments,
                              check=True, capture_output=True, timeout=30).stdout

    def project(self):
        return validate_project({"version": 1, "id": "production_test", "name": "ENGINE TEST project", "fps": 12,
                                 "width": 32, "height": 24, "clips": [], "titles": [], "tracks": [],
                                 "assets": [{"id": "a", "name": "shot_a.mkv", "path": "media/a.mkv"},
                                            {"id": "b", "name": "shot_b.mkv", "path": "media/b.mkv"},
                                            {"id": "still", "name": "still.png", "path": "media/still.png"},
                                            {"id": "sound", "name": "sound.wav", "path": "media/sound.wav"}],
                                 "settings": {"scene": {"version": 1, "name": "Preserved scene"}, "custom": {"kept": True}}}, self.root)

    def plan(self):
        return {"film": "ENGINE TEST planned film", "fps": 12, "width": 32, "height": 24,
                "shots": [{"id": "first", "filename": "shot_a.mkv", "duration_frames": 4},
                          {"id": "second", "filename": "shot_b.mkv", "duration_frames": 3}], "runtime_frames": 7}

    def bindings(self):
        return {"first": {"asset_id": "a", "in_frame": 2}, "second": {"asset_id": "b", "in_frame": 3}}

    def test_complete_conform_builds_exact_cut_preserves_state_and_renders_actual_rgb_pcm(self):
        original, plan, bindings = self.project(), self.plan(), self.bindings()
        before = copy.deepcopy(original)
        result = conform_plan(plan, original, self.root, bindings)
        candidate = result["project"]
        self.assertTrue(result["ready"])
        self.assertFalse(result["committed"])
        self.assertEqual(original, before)
        self.assertEqual(candidate["assets"], original["assets"])
        self.assertEqual(candidate["settings"]["scene"], original["settings"]["scene"])
        self.assertEqual(candidate["settings"]["custom"], original["settings"]["custom"])
        self.assertEqual([(c["asset_id"], c["start"], c["in"], c["duration"]) for c in candidate["clips"]],
                         [("a", 0, 2, 4), ("b", 4, 3, 3)])
        production = candidate["settings"]["production"]
        self.assertEqual(production["issuance_effect"], "NONE")
        self.assertEqual(production["media_identities"]["first"]["sha256"], hashlib.sha256((self.root / "media/a.mkv").read_bytes()).hexdigest())
        self.assertFalse((self.root / "project.json").exists())
        output = self.root / "ENGINE_TEST_production.mov"
        render_project(candidate, self.root, output, "prores")
        pixels = self.ffmpeg(["-i", str(output), "-map", "0:v:0", "-pix_fmt", "rgb24", "-threads", "1", "-f", "rawvideo", "pipe:1"])
        pcm = self.ffmpeg(["-i", str(output), "-map", "0:a:0", "-f", "s16le", "pipe:1"])
        self.assertEqual(len(pixels), 7 * 32 * 24 * 3, "There must be exactly seven real frames, without filler")
        for frame in range(7):
            offset = frame * 32 * 24 * 3 + (12 * 32 + 16) * 3
            r, g, b = pixels[offset:offset + 3]
            self.assertGreater(r if frame < 4 else b, 200)
            self.assertLess(b if frame < 4 else r, 25)
        self.assertEqual(len(pcm), 28000 * 2 * 2)
        self.assertGreater(max(abs(sample[0]) for sample in struct.iter_unpack("<h", pcm)), 100)

    def test_missing_footage_blocks_cut_but_plan_persists_without_changing_edit(self):
        project = self.project()
        project["clips"] = [{"id": "keep", "asset_id": "a", "track": 0, "start": 1, "in": 0, "duration": 2}]
        project = validate_project(project, self.root)
        review = review_plan(self.plan(), project, self.root)
        self.assertFalse(review["ready"])
        self.assertEqual(len(review["errors"]), 2)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            conform_plan(self.plan(), project, self.root)
        saved = prepare_plan(self.plan(), project, self.root, {"first": {"asset_id": "a", "in_frame": 1}})
        self.assertFalse(saved["replace_timeline"])
        self.assertFalse(saved["ready"])
        self.assertEqual(saved["project"]["clips"], project["clips"])
        self.assertEqual(saved["project"]["settings"]["production"]["bindings"]["first"]["in_frame"], 1)
        self.assertEqual(saved["project"]["fps"], project["fps"])
        exported = export_plan(saved["project"])
        self.assertEqual(normalize_plan(exported["document"]), saved["plan"])
        self.assertEqual(exported["plan_sha256"], saved["plan_sha256"])

    def test_short_wrong_kind_missing_id_wrong_name_and_hash_changes_block_assembly(self):
        for binding in ({"asset_id": "a", "in_frame": 9}, {"asset_id": "still"}, {"asset_id": "sound"},
                        {"asset_id": "unknown"}, {"asset_id": "b"}):
            bindings = self.bindings()
            bindings["first"] = binding
            with self.subTest(binding=binding):
                review = review_plan(self.plan(), self.project(), self.root, bindings)
                self.assertFalse(review["ready"])
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    conform_plan(self.plan(), self.project(), self.root, bindings)
        bindings = self.bindings()
        bindings["first"] = {"asset_id": "b", "allow_name_mismatch": True}
        self.assertTrue(review_plan(self.plan(), self.project(), self.root, bindings)["ready"])
        plan = self.plan()
        plan["shots"][0]["sha256"] = "0" * 64
        self.assertFalse(review_plan(plan, self.project(), self.root, self.bindings())["ready"])
        project = self.project()
        project["assets"][0]["sha256"] = "0" * 64
        self.assertFalse(review_plan(self.plan(), project, self.root, self.bindings())["ready"])

    def test_probed_handles_and_source_inventory_override_forged_client_metadata(self):
        project = self.project()
        project["assets"][0].update(duration=9999, frames=999999, width=9999)
        review = review_plan(self.plan(), project, self.root, self.bindings())
        first = review["shots"][0]
        self.assertEqual((first["available_frames"], first["head_handle_frames"], first["tail_handle_frames"]), (12, 2, 6))
        self.assertEqual(first["source_width"], 32)

    def test_format_replacement_requires_consent_for_existing_edit_and_locks_block(self):
        project = self.project()
        plan = self.plan()
        plan["width"] = 64
        self.assertEqual(conform_plan(plan, project, self.root, self.bindings())["project"]["width"], 64)
        project["clips"] = [{"id": "old", "asset_id": "a", "track": 0, "duration": 2}]
        with self.assertRaisesRegex(ValueError, "different format"):
            conform_plan(plan, project, self.root, self.bindings())
        self.assertEqual(conform_plan(plan, project, self.root, self.bindings(), replace_format=True)["project"]["width"], 64)
        project["tracks"] = [{"id": 0, "locked": True}]
        with self.assertRaisesRegex(ValueError, "Unlock"):
            conform_plan(self.plan(), project, self.root, self.bindings())

    def test_unknown_binding_keys_negative_handles_and_malformed_exports_reject(self):
        for binding in ({"unknown": {"asset_id": "a"}}, {"first": {"asset_id": "a", "in_frame": -1}},
                        {"first": {"asset_id": "a", "duration": 1}}, {"first": {"asset_id": "a", "allow_name_mismatch": 1}}):
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                review_plan(self.plan(), self.project(), self.root, binding)
        for project in ({}, {"settings": []}, {"settings": {"production": {"plan": {}}}}):
            with self.subTest(project=project), self.assertRaises(ValueError):
                export_plan(project)


if __name__ == "__main__":
    unittest.main()
