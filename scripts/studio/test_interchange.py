"""Real OTIO cut interchange, verified with upstream reader when installed.

Test media and all rendered outputs are ENGINE TEST SIGNALS ONLY.
"""
import copy
import hashlib
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
from color_pipeline import import_cube

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
        for name, color in (("plate", "blue"), ("parked", "lime")):
            cls.ffmpeg(["-f", "lavfi", "-i", f"color=c={color}:s=96x64:r=24:d=1", "-an", "-c:v", "ffv1",
                        str(cls.root / f"media/ENGINE_TEST_{name}.mkv")])
        cls.ffmpeg(["-i", str(cls.root / "media/ENGINE_TEST_plate.mkv"), "-frames:v", "1", "-threads", "1",
                    str(cls.root / "media/ENGINE_TEST_title.png")])

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

    def test_private_color_roundtrip_requires_the_project_owned_lut(self):
        project = self.project()
        lut = import_cube('TITLE "ENGINE TEST interchange"\nLUT_1D_SIZE 2\n0 0 0\n1 1 1\n', self.root)
        project['clips'][0]['color_pipeline'] = {'version': 1, 'enabled': True,
            'lut': {'sha256': lut['sha256'], 'interpolation': 'linear'}}
        project = validate_project(project, self.root)
        exported = export_otio(project, self.root)
        self.assertTrue(any('not embedded in OTIO' in warning for warning in exported['warnings']))
        restored = import_otio(exported['document'], self.project(), self.root)
        self.assertEqual(project['clips'][0]['color_pipeline'], restored['project']['clips'][0]['color_pipeline'])
        path = self.root / 'color/luts' / (lut['sha256'] + '.cube')
        original = path.read_bytes()
        path.unlink()
        try:
            with self.assertRaises(ValueError):
                import_otio(exported['document'], self.project(), self.root)
        finally:
            path.write_bytes(original)

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

    def composite_project(self):
        """A plate reached through a mask/merge and a dormant editable source."""
        project = self.project()
        project.update(fps=24, frame_rate={"numerator": 24, "denominator": 1})
        project["assets"].extend({"id": name, "path": f"media/ENGINE_TEST_{name}.mkv"}
                                 for name in ("plate", "parked"))
        graph = {"version": 1, "nodes": [
            {"id": "source", "type": "source", "inputs": [], "params": {}},
            {"id": "plate", "type": "media_source", "inputs": [], "params": {"asset_id": "plate", "duration": 8}},
            {"id": "masked", "type": "mask", "inputs": ["plate"],
             "params": {"shape": "rectangle", "x": .75, "y": .5, "width": .5, "height": 1}},
            {"id": "merge", "type": "merge", "inputs": ["source", "masked"], "params": {}},
            {"id": "parked", "type": "media_source", "inputs": [], "params": {"asset_id": "parked", "duration": 8}},
        ], "output": "merge"}
        project["clips"] = [
            {"id": "composite", "asset_id": "picture", "track": 0, "start": 0, "in": 0, "duration": 8,
             "compositor": graph},
            {"id": "audio", "asset_id": "sound", "track": -1, "start": 0, "in": 0, "duration": 8,
             "volume": .5}]
        return validate_project(project, self.root)

    def test_cross_project_compositor_dependencies_preserve_rgb_pcm_and_dormant_nodes(self):
        source = self.composite_project()
        document = export_otio(source, self.root)["document"]
        identities = document["metadata"]["cinematicum"]["asset_sha256"]
        self.assertEqual(set(identities), {"picture", "sound", "plate", "parked"})
        for asset in source["assets"]:
            self.assertEqual(identities[asset["id"]], hashlib.sha256((self.root / asset["path"]).read_bytes()).hexdigest())
        # Copy bytes into a distinct project directory: neither file paths nor
        # asset IDs survive. Interchange must match content, then remap every
        # nested reference, including the disconnected node retained for edits.
        with tempfile.TemporaryDirectory(prefix="cinematicum-ENGINE-TEST-OTIO-destination-") as directory:
            destination_dir = Path(directory)
            (destination_dir / "media").mkdir()
            destination = copy.deepcopy(source)
            destination.update(id="different_project", clips=[], titles=[])
            for index, asset in enumerate(destination["assets"]):
                source_path = self.root / asset["path"]
                asset["id"] = "fresh_" + asset["id"]
                asset["path"] = f"media/copied_{index}{source_path.suffix}"
                shutil.copyfile(source_path, destination_dir / asset["path"])
            before = copy.deepcopy(destination)
            document_before = copy.deepcopy(document)
            result = import_otio(document, destination, destination_dir)
            restored = result["project"]
            self.assertEqual(restored["clips"][0]["asset_id"], "fresh_picture")
            nodes = {node["id"]: node for node in restored["clips"][0]["compositor"]["nodes"]}
            self.assertEqual(nodes["plate"]["params"]["asset_id"], "fresh_plate")
            self.assertEqual(nodes["parked"]["params"]["asset_id"], "fresh_parked")
            self.assertEqual(destination, before)
            self.assertEqual(document, document_before)
            self.assertFalse((destination_dir / "project.json").exists())
            outputs = []
            for name, project, project_dir in (("source_composite", source, self.root),
                                               ("destination_composite", restored, destination_dir)):
                path = project_dir / ("ENGINE_TEST_" + name + ".mov")
                render_project(project, project_dir, path, "prores")
                outputs.append((self.ffmpeg(["-i", str(path), "-map", "0:v:0", "-pix_fmt", "rgb24", "-threads", "1", "-f", "rawvideo", "pipe:1"]),
                                self.ffmpeg(["-i", str(path), "-map", "0:a:0", "-f", "s16le", "pipe:1"])))
            self.assertEqual(len(outputs[0][0]), 8 * 96 * 64 * 3)
            self.assertEqual(outputs[0], outputs[1], "Cross-project dependencies must preserve decoded pixels and audio samples")

    def test_reused_graph_source_id_cannot_substitute_unrelated_media(self):
        source = self.composite_project()
        document = export_otio(source, self.root)["document"]
        destination = copy.deepcopy(source)
        destination.update(id="collision_project", clips=[])
        asset = next(a for a in destination["assets"] if a["id"] == "plate")
        asset["path"] = "media/ENGINE_TEST_parked.mkv"
        before = copy.deepcopy(destination)
        with self.assertRaisesRegex(ValueError, "Unresolved OTIO media"):
            import_otio(document, destination, self.root)
        self.assertEqual(destination, before)
        # A collision is not fatal when the correct bytes were imported with a
        # fresh ID: hash matching must choose those bytes instead of the old ID.
        destination["assets"].append({"id": "correct_plate", "path": "media/ENGINE_TEST_plate.mkv"})
        result = import_otio(document, destination, self.root)["project"]
        plate = next(n for n in result["clips"][0]["compositor"]["nodes"] if n["id"] == "plate")
        self.assertEqual(plate["params"]["asset_id"], "correct_plate")

    def test_private_raster_titles_are_remapped_but_unused_assets_are_not_dependencies(self):
        source = self.composite_project()
        source["assets"].extend([
            {"id": "raster", "path": "media/ENGINE_TEST_title.png"},
            {"id": "unused", "path": "media/ENGINE_TEST_parked.mkv"}])
        source["titles"] = [{"id": "title", "text": "ENGINE TEST raster", "start": 0, "duration": 8,
                             "asset_id": "raster"}]
        source = validate_project(source, self.root)
        document = export_otio(source, self.root)["document"]
        self.assertNotIn("unused", document["metadata"]["cinematicum"]["asset_sha256"])
        self.assertIn("raster", document["metadata"]["cinematicum"]["asset_sha256"])
        destination = copy.deepcopy(source)
        destination.update(id="title_destination", clips=[], titles=[])
        destination["assets"] = [asset for asset in destination["assets"] if asset["id"] != "unused"]
        for asset in destination["assets"]:
            asset["id"] = "fresh_" + asset["id"]
        restored = import_otio(document, destination, self.root)["project"]
        self.assertEqual(restored["titles"][0]["asset_id"], "fresh_raster")
        missing = copy.deepcopy(destination)
        missing["assets"] = [asset for asset in missing["assets"] if asset["id"] != "fresh_raster"]
        with self.assertRaisesRegex(ValueError, "Unresolved OTIO media"):
            import_otio(document, missing, self.root)

    def test_private_dependencies_require_complete_valid_identities_even_for_legacy_same_ids(self):
        source = self.composite_project()
        document = export_otio(source, self.root)["document"]
        # 0.7's incomplete export omitted graph-only media. Same IDs cannot be
        # used as evidence of unchanged bytes, including in the source project.
        for missing in ("plate", "parked", "picture"):
            legacy = copy.deepcopy(document)
            del legacy["metadata"]["cinematicum"]["asset_sha256"][missing]
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "complete media dependencies"):
                import_otio(legacy, source, self.root)
        for table in (None, [], {"plate": "invalid"}, {"bad/path": "0" * 64}):
            malformed = copy.deepcopy(document)
            malformed["metadata"]["cinematicum"]["asset_sha256"] = table
            with self.subTest(table=table), self.assertRaisesRegex(ValueError, "asset_sha256"):
                import_otio(malformed, source, self.root)

    def test_explicit_different_bytes_cannot_restore_private_authoring(self):
        source = self.composite_project()
        document = export_otio(source, self.root)["document"]
        plate_digest = document["metadata"]["cinematicum"]["asset_sha256"]["plate"]
        for relink in ({"sha256:" + plate_digest: "parked"},
                       {"media/ENGINE_TEST_picture.mkv": "plate"}):
            with self.subTest(relink=relink), self.assertRaisesRegex(ValueError, "media identity mismatch"):
                import_otio(document, source, self.root, relink)
        # Externally edited cuts may still explicitly relink to different media;
        # the public-cut path warns and does not restore the private composite.
        external = copy.deepcopy(document)
        external["tracks"]["children"] = [track for track in external["tracks"]["children"]
                                           if track["metadata"]["cinematicum"]["role"] != "embedded_audio"]
        self.first_clip(external)["source_range"]["start_time"]["value"] = 1
        result = import_otio(external, source, self.root, {"media/ENGINE_TEST_picture.mkv": "plate"})
        self.assertTrue(any("different media content" in warning for warning in result["warnings"]))
        self.assertNotIn("compositor", result["project"]["clips"][0])

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
