"""Real OTIO cut interchange, verified with upstream reader when installed.

Test media and all rendered outputs are ENGINE TEST SIGNALS ONLY.
"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from engine import render_project, validate_project
from interchange import export_otio, import_otio, _public_digest
from scene import validate_scene

try:
    import opentimelineio as otio
except ImportError:
    otio = None


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class InterchangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="cinematicum-ENGINE-TEST-OTIO-")
        cls.root = Path(cls.temp.name)
        (cls.root / "media").mkdir()
        cls.ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=96x64:r=24:d=4", "-f", "lavfi", "-i", "sine=f=880:r=48000:d=4",
                    "-c:v", "ffv1", "-c:a", "pcm_s16le", str(cls.root / "media/ENGINE_TEST_picture.mkv")])
        cls.ffmpeg(["-f", "lavfi", "-i", "sine=f=440:r=48000:d=4", "-c:a", "pcm_s16le", str(cls.root / "media/ENGINE_TEST_sound.wav")])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def ffmpeg(args):
        return subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1", "-threads", "1"] + args,
                              capture_output=True, check=True, timeout=30).stdout

    def project(self):
        p = {"version": 1, "id": "otio_test", "name": "ENGINE TEST OTIO", "fps": 30000/1001,
             "frame_rate": {"numerator": 30000, "denominator": 1001}, "width": 96, "height": 64,
             "assets": [{"id": "picture", "path": "media/ENGINE_TEST_picture.mkv"},
                        {"id": "sound", "path": "media/ENGINE_TEST_sound.wav"}],
             "clips": [{"id": "first", "asset_id": "picture", "track": 0, "start": 2, "in": .5, "duration": 24,
                        "animation_duration": 48, "animation_offset": 2,
                        "keyframes": [{"frame": 0, "opacity": .2, "interpolation": "ease_in"}, {"frame": 47, "opacity": 1}],
                        "grade": {"exposure": .3}},
                       {"id": "second", "asset_id": "picture", "track": 0, "start": 31, "in": 25, "duration": 12},
                       {"id": "soundtrack", "asset_id": "sound", "track": -1, "start": 0, "in": 0, "duration": 48,
                        "volume": .7, "audio": {"fade_in": 6, "fade_out": 8}}],
             "tracks": [{"id": 0, "name": "Main"}, {"id": 2, "name": "Unused"}, {"id": -1, "name": "Sound", "gain": .8}],
             "titles": [], "settings": {"custom_editor_state": {"selected": "first"}}}
        return validate_project(p, self.root)

    @staticmethod
    def without_metadata(value):
        if isinstance(value, dict):
            return {key: ({} if key == "metadata" else InterchangeTests.without_metadata(item)) for key, item in value.items()}
        if isinstance(value, list):
            return [InterchangeTests.without_metadata(item) for item in value]
        return value

    def mapping(self):
        return {"media/ENGINE_TEST_picture.mkv": "picture", "media/ENGINE_TEST_sound.wav": "sound"}

    @staticmethod
    def first_clip(document):
        return next(c for t in document["tracks"]["children"] for c in t["children"] if c["OTIO_SCHEMA"].startswith("Clip."))

    def test_lossless_self_roundtrip_uses_real_media_identity_and_is_unsaved(self):
        p = self.project()
        before = copy.deepcopy(p)
        exported = export_otio(p, self.root)
        self.assertTrue(any("unprocessed" in warning for warning in exported["warnings"]))
        self.assertEqual(exported["document"]["metadata"]["cinematicum"]["frame_rate"], p["frame_rate"])
        imported = import_otio(json.dumps(exported["document"]), p, self.root)
        self.assertEqual(imported["project"], p)
        self.assertEqual(p, before)
        self.assertTrue(any("No project has been saved" in warning for warning in imported["warnings"]))
        self.assertFalse((self.root / "project.json").exists())

    @unittest.skipUnless(otio, "Install official OpenTimelineIO to independently verify the wire format")
    def test_official_otio_reader_and_writer_preserve_the_exchange(self):
        p = self.project()
        exported = export_otio(p, self.root)
        timeline = otio.adapters.read_from_string(json.dumps(exported["document"]), adapter_name="otio_json")
        self.assertIsInstance(timeline, otio.schema.Timeline)
        self.assertEqual(timeline.duration().value, 48)
        self.assertAlmostEqual(timeline.duration().rate, 30000/1001)
        self.assertEqual(sum(isinstance(item, otio.schema.Clip) for track in timeline.tracks for item in track), 5,
                         "Video source audio must also be represented as editable Audio-track cuts")
        main = timeline.tracks[0]
        self.assertIsInstance(main[0], otio.schema.Gap)
        self.assertEqual(main.range_of_child_at_index(1).start_time.value, 2)
        self.assertEqual(main[1].source_range.start_time.value, .5)
        serialized = otio.adapters.write_to_string(timeline, adapter_name="otio_json")
        result = import_otio(serialized, p, self.root)
        self.assertEqual(result["project"], p, "The upstream serializer must not invalidate the lossless metadata roundtrip")

    def test_roundtripped_authoring_still_renders_identical_picture_and_sound(self):
        p = self.project()
        imported = import_otio(export_otio(p, self.root)["document"], p, self.root)["project"]
        outputs = []
        for name, project in (("original", p), ("roundtrip", imported)):
            path = self.root / ("ENGINE_TEST_" + name + ".mov")
            render_project(project, self.root, path, "prores")
            outputs.append((self.ffmpeg(["-i", str(path), "-map", "0:v:0", "-pix_fmt", "rgb24", "-threads", "1", "-f", "rawvideo", "pipe:1"]),
                            self.ffmpeg(["-i", str(path), "-map", "0:a:0", "-f", "s16le", "pipe:1"])))
        self.assertEqual(outputs[0], outputs[1])

    def test_external_cuts_resolve_only_explicit_existing_asset_mappings(self):
        p = self.project()
        doc = self.without_metadata(export_otio(p, self.root)["document"])
        with patch("interchange._sha256", side_effect=AssertionError("Unmapped paths must never be opened")):
            with self.assertRaisesRegex(ValueError, "Unresolved OTIO media"):
                import_otio(doc, p, self.root)
        result = import_otio(doc, p, self.root, self.mapping())
        clips = result["project"]["clips"]
        self.assertEqual(len(clips), 5)
        self.assertEqual([(c["start"], c["duration"]) for c in clips if c["track"] >= 0], [(2, 24), (31, 12)])
        self.assertTrue(all(c["volume"] == 0 for c in clips if c["track"] >= 0))
        self.assertTrue(any("avoid duplicated audio" in message for message in result["warnings"]))

    def test_source_timecode_and_sample_rate_units_are_converted_without_rounding_cuts(self):
        p = self.project()
        doc = self.without_metadata(export_otio(p, self.root)["document"])
        item = self.first_clip(doc)
        reference = item["media_references"]["DEFAULT_MEDIA"]
        item["source_range"]["start_time"]["value"] += 100
        reference["available_range"]["start_time"]["value"] = 100
        # A 24-frame cut at 30000/1001 is exactly 38,438.4 samples; OTIO's
        # time coordinates may use an audio clock without changing the edit.
        item["source_range"]["duration"].update(value=38438.4, rate=48000)
        result = import_otio(doc, p, self.root, self.mapping())["project"]
        first = next(c for c in result["clips"] if c["track"] == 0)
        self.assertEqual(first["in"], .5)
        self.assertEqual(first["duration"], 24)

    def test_changed_public_cuts_do_not_restore_stale_private_effects(self):
        p = self.project()
        doc = export_otio(p, self.root)["document"]
        self.first_clip(doc)["source_range"]["start_time"]["value"] += 1
        result = import_otio(doc, p, self.root)
        self.assertTrue(any("stale CINEMATICUM" in warning for warning in result["warnings"]))
        self.assertEqual(result["project"]["clips"][0]["in"], 1.5)
        self.assertEqual(result["project"]["clips"][0]["keyframes"], [])

    def test_unknown_effect_warns_but_timewarps_transitions_and_nesting_refuse(self):
        p = self.project()
        base = self.without_metadata(export_otio(p, self.root)["document"])
        self.first_clip(base)["effects"] = [{"OTIO_SCHEMA": "Effect.1", "name": "External blur", "effect_name": "Blur"}]
        result = import_otio(base, p, self.root, self.mapping())
        self.assertTrue(any("External blur is not applied" in warning for warning in result["warnings"]))
        for schema in ("TimeEffect.1", "LinearTimeWarp.1", "FreezeFrame.1"):
            doc = copy.deepcopy(base)
            self.first_clip(doc)["effects"][0]["OTIO_SCHEMA"] = schema
            with self.subTest(schema=schema), self.assertRaisesRegex(ValueError, "timewarp"):
                import_otio(doc, p, self.root, self.mapping())
        for schema in ("Transition.1", "Stack.1", "Track.1"):
            doc = copy.deepcopy(base)
            self.first_clip(doc)["OTIO_SCHEMA"] = schema
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                import_otio(doc, p, self.root, self.mapping())

    def test_export_rejects_overlap_retime_and_reverse(self):
        for change in ({"speed": 2}, {"reverse": True}, {"start": 20}):
            p = self.project()
            p["clips"][1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                export_otio(p, self.root)

    def test_untrusted_paths_unknown_assets_fractional_cuts_and_nonfinite_values_refuse(self):
        p = self.project()
        base = self.without_metadata(export_otio(p, self.root)["document"])
        for target in ("file:///etc/passwd", "https://example.com/video.mov", "../../private.mov"):
            doc = copy.deepcopy(base)
            self.first_clip(doc)["media_references"]["DEFAULT_MEDIA"]["target_url"] = target
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "Unresolved"):
                import_otio(doc, p, self.root, self.mapping())
        bad = copy.deepcopy(base)
        self.first_clip(bad)["source_range"]["duration"]["value"] = 1.25
        with self.assertRaisesRegex(ValueError, "between project frames"):
            import_otio(bad, p, self.root, self.mapping())
        with self.assertRaises(ValueError):
            import_otio(base, p, self.root, {"media/ENGINE_TEST_picture.mkv": "not_imported"})
        with self.assertRaises(ValueError):
            import_otio('{"OTIO_SCHEMA":"Timeline.1","value":NaN}', p, self.root)
        with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
            import_otio('{"OTIO_SCHEMA":"Timeline.1","OTIO_SCHEMA":"Stack.1"}', p, self.root)

    def test_private_snapshot_cannot_override_public_timing_or_linked_audio(self):
        p = self.project()
        doc = export_otio(p, self.root)["document"]
        doc["metadata"]["cinematicum"]["project"]["clips"][0]["start"] = 99
        with self.assertRaisesRegex(ValueError, "Private CINEMATICUM timing"):
            import_otio(doc, p, self.root)
        doc = export_otio(p, self.root)["document"]
        companion = next(t for t in doc["tracks"]["children"] if t["metadata"]["cinematicum"]["role"] == "embedded_audio")
        item = next(c for c in companion["children"] if c["OTIO_SCHEMA"] == "Clip.2")
        item["source_range"]["start_time"]["value"] += 1
        doc["metadata"]["cinematicum"]["public_sha256"] = _public_digest(doc)
        with self.assertRaisesRegex(ValueError, "Linked source audio"):
            import_otio(doc, p, self.root)

    @staticmethod
    def malformed_settings():
        return [None, [], "invalid", 0, False,
                {"scene": []}, {"scene": {"version": 2}},
                {"scene": {"version": 1, "camera": {"position": [0, 0, 0], "target": [0, 0, 0]}}},
                {"scene": {"version": 1, "objects": [{"id": "bad_mesh", "type": "mesh", "mesh": {}}]}}]

    def test_export_rejects_malformed_private_settings_and_scene(self):
        for settings in self.malformed_settings():
            p = self.project()
            p["settings"] = copy.deepcopy(settings)
            before = copy.deepcopy(p)
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                export_otio(p, self.root)
            self.assertEqual(p, before, "Rejected export must not change the current project")

    def test_import_rejects_malformed_private_settings_and_scene_before_apply(self):
        p = self.project()
        exported = export_otio(p, self.root)["document"]
        before = copy.deepcopy(p)
        for settings in self.malformed_settings():
            doc = copy.deepcopy(exported)
            doc["metadata"]["cinematicum"]["project"]["settings"] = copy.deepcopy(settings)
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                import_otio(doc, p, self.root)
            self.assertEqual(p, before, "Rejected private metadata must not change the destination project")
        self.assertFalse((self.root / "project.json").exists())

    def test_private_scene_is_normalized_for_export_and_import_without_mutation(self):
        p = self.project()
        scene = {"version": 1, "width": 1280, "height": 720, "camera": {"fov": 50},
                 "world": {"color": "#ABCDEF"},
                 "objects": [{"id": "authored_cube", "type": "cube", "material": {"color": "#AABBCC"}}]}
        p["settings"]["scene"] = copy.deepcopy(scene)
        before = copy.deepcopy(p)
        expected = validate_scene(scene, width=p["width"], height=p["height"])
        doc = export_otio(p, self.root)["document"]
        self.assertEqual(doc["metadata"]["cinematicum"]["project"]["settings"]["scene"], expected)
        self.assertEqual(p, before, "Export normalization must not mutate unsaved authoring data")
        # Replace private metadata with a valid but noncanonical recipe. Its
        # public cut digest remains unchanged, so this exercises import itself.
        doc["metadata"]["cinematicum"]["project"]["settings"]["scene"] = copy.deepcopy(scene)
        imported = import_otio(doc, p, self.root)["project"]
        self.assertEqual(imported["settings"]["scene"], expected)
        self.assertEqual(imported["settings"]["custom_editor_state"], p["settings"]["custom_editor_state"])
        self.assertEqual(p, before)
        self.assertEqual(doc["metadata"]["cinematicum"]["project"]["settings"]["scene"], scene)
        without_settings = self.project()
        without_settings.pop("settings")
        self.assertEqual(export_otio(without_settings, self.root)["document"]["metadata"]["cinematicum"]["project"]["settings"], {})
        self.assertNotIn("settings", without_settings)

    def test_trailing_gap_is_not_silently_discarded(self):
        p = self.project()
        doc = self.without_metadata(export_otio(p, self.root)["document"])
        track = doc["tracks"]["children"][-1]
        gap = copy.deepcopy(doc["tracks"]["children"][0]["children"][0])
        gap["source_range"]["duration"]["value"] = 12
        track["children"].append(gap)
        with self.assertRaisesRegex(ValueError, "Trailing/all-gap"):
            import_otio(doc, p, self.root, self.mapping())


if __name__ == "__main__":
    unittest.main()
