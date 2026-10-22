"""Real source-media acceptance for simultaneous cameras and fixed source sound.

The fixture's pixels encode every source frame. Independent PCM truth comes
from decoding its original files, never from the render graph under test.
Missing FFmpeg/NumPy is a failed acceptance prerequisite, not a skipped gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

from editorial import apply_action
from engine import probe_media, render_project, validate_project
from multicam import resolve_audio


def ffmpeg(arguments, payload=None, timeout=15):
    binary = shutil.which("ffmpeg")
    if not binary or not shutil.which("ffprobe"):
        raise RuntimeError("The actual multicamera monitor gate requires FFmpeg and FFprobe.")
    return subprocess.run([binary, "-v", "error", "-nostdin", "-y", "-threads", "1",
                           "-filter_threads", "1", "-filter_complex_threads", "1", *map(str, arguments)],
                          input=payload, capture_output=True, check=True, timeout=timeout).stdout


def make_fixture(root):
    root = Path(root); (root / "media").mkdir(parents=True); (root / "truth").mkdir()
    samples = np.arange(6 * 48000) / 48000
    specifications = [("camera_a", (240, 12, 8), [[(.15, 880), (.20, 990)]]),
                      ("camera_b", (8, 12, 240), [[(.1, 220), (.2, 330)], [(.3, 440), (.4, 660)]])]
    assets = []
    for name, color, streams in specifications:
        frames = np.zeros((144, 64, 96, 3), dtype=np.uint8); frames[:] = color
        for frame in range(144):
            for bit in range(8):
                frames[frame, 0:8, bit * 8:(bit + 1) * 8] = 255 if frame & (1 << bit) else 0
        raw = root / "truth" / (name + ".rgb"); raw.write_bytes(frames.tobytes())
        argv = ["-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "96x64", "-framerate", "24", "-i", raw]
        for index, channels in enumerate(streams):
            value = np.column_stack([amplitude * np.sin(2 * np.pi * frequency * samples) for amplitude, frequency in channels]).astype("<f4")
            path = root / "truth" / f"{name}_{index}.f32le"; path.write_bytes(value.tobytes())
            argv += ["-f", "f32le", "-ar", "48000", "-ac", "2", "-i", path]
        argv += ["-map", "0:v"]
        for index in range(len(streams)):
            argv += ["-map", f"{index + 1}:a"]
        path = root / "media" / (name + ".mov")
        # H.264 lossless mode declares High 4:4:4 Predictive even with 4:2:0
        # pixels. Use a normal browser/native-decodable profile; independent
        # frame counters remain binary and the original sound remains PCM.
        ffmpeg(argv + ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-profile:v", "baseline", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-threads", "1", path])
        assets.append({"id": name, "name": "ENGINE TEST " + name, "path": "media/" + path.name,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **probe_media(path)})
        for index in range(len(streams)):
            data = ffmpeg(["-i", path, "-map", f"0:a:{index}", "-ac", "2", "-ar", "48000", "-f", "f32le", "pipe:1"])
            (root / "truth" / f"{name}_{index}_decoded.f32le").write_bytes(data)
    return assets


def fixture_project(assets):
    return {"version": 1, "id": "monitor_test", "name": "ENGINE TEST multicamera monitor",
            "fps": 24, "width": 96, "height": 64, "assets": copy.deepcopy(assets), "clips": [], "titles": [], "tracks": []}


def create_group(project, root):
    return apply_action(project, "multicam_create", {"name": "ENGINE TEST two original cameras", "start": 0, "track": 0,
                        "angles": [{"asset_id": project["assets"][0]["id"], "in": 12},
                                   {"asset_id": project["assets"][1]["id"], "in": 24}]}, root)["project"]


def decoded_movie(path):
    pcm = np.frombuffer(ffmpeg(["-i", path, "-map", "0:a:0", "-ac", "2", "-ar", "48000", "-f", "f32le", "pipe:1"]), "<f4").reshape(-1, 2)
    rgb = np.frombuffer(ffmpeg(["-i", path, "-map", "0:v:0", "-pix_fmt", "rgb24", "-f", "rawvideo", "-threads", "1", "pipe:1"]), np.uint8).reshape(-1, 64, 96, 3)
    indices = sum((rgb[:, 4, bit * 8 + 4, :].mean(axis=1) > 127).astype(np.int32) * (1 << bit) for bit in range(8))
    return pcm, rgb, indices


class ActualMulticamMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="cinematicum-monitor-ENGINE-TEST-")
        cls.root = Path(cls.temp.name); cls.assets = make_fixture(cls.root)
        cls.original_hashes = {a["path"]: a["sha256"] for a in cls.assets}
        cls.sound = np.fromfile(cls.root / "truth/camera_b_1_decoded.f32le", "<f4").reshape(-1, 2)

    @classmethod
    def tearDownClass(cls):
        for path, digest in cls.original_hashes.items():
            if hashlib.sha256((cls.root / path).read_bytes()).hexdigest() != digest:
                raise AssertionError("The acceptance changed original source bytes: " + path)
        cls.temp.cleanup()

    def project(self):
        return create_group(fixture_project(self.assets), self.root)

    def locked(self):
        p = self.project(); clip = p["clips"][0]; clip["volume"] = .5; clip["audio"]["pan"] = .25
        return apply_action(p, "multicam_audio_lock", {"clip_id": clip["id"], "angle_id": p["multicam_groups"][0]["angles"][1]["id"],
                            "stream_index": 2, "channels": [1, 0]}, self.root)["project"]

    def cut(self, p, frame=48):
        return apply_action(p, "multicam_cut", {"clip_id": p["clips"][0]["id"], "angle_id": p["multicam_groups"][0]["angles"][1]["id"],
                            "frame": frame}, self.root)["project"]

    def render(self, p, label, root=None):
        target = self.root / (label + ".mov"); render_project(p, root or self.root, target, "prores")
        return decoded_movie(target)

    def assert_pcm(self, actual, expected):
        self.assertEqual(actual.shape, expected.shape)
        self.assertLessEqual(float(np.max(np.abs(actual - expected))), 1 / 32768 + 1e-7)

    def test_monitor_uses_shared_actual_source_clock_after_cut(self):
        p = self.cut(self.locked()); original = copy.deepcopy(p)
        for frame in (0, 24, 47, 48, 119):
            clip = next(c for c in p["clips"] if c["start"] <= frame < c["start"] + c["duration"])
            result = apply_action(p, "multicam_monitor", {"clip_id": clip["id"], "frame": frame}, self.root)
            self.assertNotIn("project", result)
            plan = result["monitor"]
            self.assertEqual([a["source_frame"] for a in plan["angles"]], [frame + 12, frame + 24])
            self.assertTrue(all(a["available"] and a["url"].endswith(a["asset_id"]) for a in plan["angles"]))
            self.assertEqual(plan["audio_lock"]["stream_index"], 2)
        self.assertEqual(p, original)

    def test_every_picture_frame_and_pcm_sample_keep_locked_original_sound_across_cut(self):
        initial = self.locked(); p = self.cut(initial); original = copy.deepcopy(initial)
        self.assertEqual(len(p["clips"]), 2); self.assertEqual(initial, original)
        self.assertNotIn("stream_index", p["clips"][1]["audio"])
        pcm, rgb, indices = self.render(p, "locked_cut")
        self.assertEqual(indices.tolist(), list(range(12, 60)) + list(range(72, 144)))
        self.assertTrue(np.all(rgb[:48, 32, 48, 0] > 220)); self.assertTrue(np.all(rgb[48:, 32, 48, 2] > 220))
        self.assert_pcm(pcm, self.sound[48000:288000, ::-1] * np.asarray([.375, .5]))
        resolved = [resolve_audio(p, c, {a["id"]: a for a in p["assets"]}) for c in p["clips"]]
        self.assertEqual([(c["in"], a["id"], c["audio"]["channels"]) for c, a in resolved], [(24, "camera_b", [1, 0]), (72, "camera_b", [1, 0])])

    def test_source_audio_controls_update_group_mapping_without_rewriting_picture_route(self):
        p = self.cut(self.locked()); authored = copy.deepcopy(p["clips"])
        mapped = apply_action(p, "audio_map", {"clip_id": p["clips"][0]["id"], "stream_index": 1, "channels": [0, 0]}, self.root)["project"]
        self.assertEqual(mapped["clips"], authored)
        pcm, _, _ = self.render(mapped, "mapped_group")
        source = np.fromfile(self.root / "truth/camera_b_0_decoded.f32le", "<f4").reshape(-1, 2)[48000:288000]
        self.assert_pcm(pcm, source[:, [0, 0]] * np.asarray([.375, .5]))
        reset = apply_action(mapped, "audio_map", {"clip_id": mapped["clips"][1]["id"], "stream_index": None, "channels": None}, self.root)["project"]
        self.assertEqual(reset["multicam_groups"][0]["audio_lock"]["stream_index"], 1)
        self.assertIsNone(reset["multicam_groups"][0]["audio_lock"]["channels"])

    def test_silent_picture_camera_still_uses_locked_original_sound(self):
        path = self.root / "media/silent_picture.mov"
        ffmpeg(["-i", self.root / "media/camera_a.mov", "-map", "0:v:0", "-c:v", "copy", "-an", path])
        silent = {"id": "silent_picture", "name": "ENGINE TEST silent picture", "path": "media/silent_picture.mov",
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **probe_media(path)}
        p = create_group(fixture_project([silent, self.assets[1]]), self.root)
        p = apply_action(p, "multicam_audio_lock", {"clip_id": p["clips"][0]["id"], "angle_id": p["multicam_groups"][0]["angles"][1]["id"],
                         "stream_index": 2, "channels": [1, 0]}, self.root)["project"]
        pcm, _, _ = self.render(p, "silent_picture_fixed_sound")
        self.assert_pcm(pcm, self.sound[48000:288000, ::-1])

    def test_unlock_restores_follow_picture_sound_with_authored_gain_and_pan(self):
        p = self.cut(self.locked())
        p = apply_action(p, "multicam_audio_lock", {"clip_id": p["clips"][0]["id"], "angle_id": None}, self.root)["project"]
        self.assertNotIn("audio_lock", p["multicam_groups"][0])
        pcm, _, _ = self.render(p, "follow_picture")
        first = np.fromfile(self.root / "truth/camera_a_0_decoded.f32le", "<f4").reshape(-1, 2)[24000:120000]
        second = np.fromfile(self.root / "truth/camera_b_0_decoded.f32le", "<f4").reshape(-1, 2)[144000:288000]
        self.assert_pcm(pcm, np.concatenate([first, second]) * np.asarray([.375, .5]))

    def test_saved_json_and_archive_relocation_preserve_lock_and_exact_movie(self):
        from project_archive import export_archive, import_archive
        p = self.cut(self.locked()); p["revision"] = 1
        reopened = validate_project(json.loads(json.dumps(p)), self.root)
        self.assertEqual(reopened, p)
        archive = self.root / "locked.cinematicum.zip"; export_archive(p, self.root, archive)
        restored_root = self.root / "restored"; restored_root.mkdir()
        restored = import_archive(archive, restored_root)
        self.assertEqual(restored["multicam_groups"], p["multicam_groups"])
        original = self.render(p, "before_archive"); replay = self.render(restored, "after_archive", restored_root / restored["id"])
        self.assertTrue(np.array_equal(original[0], replay[0])); self.assertTrue(np.array_equal(original[1], replay[1]))

    def test_nested_instances_keep_locked_audio_gain_and_original_clock(self):
        p = self.cut(self.locked()); child = {"id": "child", "name": "Camera sequence", "clips": p["clips"], "titles": [], "tracks": []}
        p.update(sequence_id="main", sequence_name="Main", sequences=[child], clips=[{"id": "nested", "sequence_id": "child", "start": 0, "in": 24, "duration": 72, "track": 0, "volume": .5}])
        pcm, _, indices = self.render(p, "nested")
        self.assertEqual(indices.tolist(), list(range(36, 60)) + list(range(72, 120)))
        self.assert_pcm(pcm, self.sound[96000:240000, ::-1] * np.asarray([.1875, .25]))

    def test_reversed_locked_movie_keeps_correct_source_span(self):
        p = self.locked(); p["clips"][0]["duration"] = 24; p["clips"][0]["reverse"] = True
        pcm, _, indices = self.render(p, "reversed")
        self.assertEqual(indices.tolist(), list(range(35, 11, -1)))
        self.assert_pcm(pcm, self.sound[48000:96000][::-1, ::-1] * np.asarray([.375, .5]))
        plan = apply_action(p, "multicam_monitor", {"clip_id": p["clips"][0]["id"], "frame": 5}, self.root)["monitor"]
        self.assertFalse(plan["cuttable"]); self.assertEqual([a["source_frame"] for a in plan["angles"]], [30, 42])

    def test_ntsc_picture_cuts_do_not_drop_or_repeat_locked_pcm_samples(self):
        initial = fixture_project(self.assets); initial.update(fps=29.97, frame_rate={"numerator": 30000, "denominator": 1001})
        initial = create_group(initial, self.root); clip = initial["clips"][0]
        p = apply_action(initial, "multicam_audio_lock", {"clip_id": clip["id"], "angle_id": initial["multicam_groups"][0]["angles"][1]["id"],
                         "stream_index": 2, "channels": [1, 0]}, self.root)["project"]
        baseline, _, _ = self.render(p, "ntsc_uncut")
        for index, frame in enumerate((1, 2, 37, 69, 129)):
            clip = next(c for c in p["clips"] if c["start"] <= frame < c["start"] + c["duration"])
            p = apply_action(p, "multicam_cut", {"clip_id": clip["id"], "angle_id": p["multicam_groups"][0]["angles"][(index + 1) % 2]["id"], "frame": frame}, self.root)["project"]
        actual, _, _ = self.render(p, "ntsc_cut")
        self.assertTrue(np.array_equal(actual, baseline), float(np.max(np.abs(actual - baseline))))

    def test_retimed_monitor_clock_and_nested_speed_export_keep_selected_stream(self):
        p = self.locked(); p["clips"][0].update(duration=48, speed=1.5)
        plan = apply_action(p, "multicam_monitor", {"clip_id": p["clips"][0]["id"], "frame": 8}, self.root)["monitor"]
        self.assertEqual([a["source_frame"] for a in plan["angles"]], [24, 36]); self.assertFalse(plan["cuttable"])
        actual, _, _ = self.render(p, "retimed")
        # Independent demux/map/trim/tempo truth; no CINEMATICUM render helper.
        truth = np.frombuffer(ffmpeg(["-i", self.root / "media/camera_b.mov", "-map", "0:2", "-af",
            "pan=stereo|c0=c1|c1=c0,atrim=start_sample=48000:end_sample=192000,asetpts=PTS-STARTPTS,atempo=1.5,apad,atrim=end_sample=96000",
            "-ac", "2", "-ar", "48000", "-f", "f32le", "pipe:1"]), "<f4").reshape(-1, 2)
        self.assert_pcm(actual, truth * np.asarray([.375, .5]))

    def test_clock_hash_rate_and_angle_edits_refuse_stale_lock(self):
        base = self.locked()
        mutations = [lambda p: p["multicam_groups"][0]["angles"][1].update({"in": 25}),
                     lambda p: p["assets"][1].update(sha256="a" * 64),
                     lambda p: p.update(fps=25, frame_rate={"numerator": 25, "denominator": 1}),
                     lambda p: p["multicam_groups"][0]["audio_lock"]["clock"]["angles"][0].update({"in": True}),
                     lambda p: p["clips"][0]["multicam"].update(angle_id="missing")]
        for mutation in mutations:
            p = copy.deepcopy(base); mutation(p)
            with self.subTest(p=p["multicam_groups"]), self.assertRaisesRegex(ValueError, "stale|angle"):
                validate_project(p, self.root)

    def test_locked_source_range_and_invalid_channels_refuse_without_mutation(self):
        base = self.locked()
        for change in ({"stream_index": 0}, {"stream_index": True}, {"channels": [2, 0]}, {"channels": [True, 0]}, {"channels": [0]}, {"unknown": 1}, {"angle_id": "missing"}):
            original = copy.deepcopy(base)
            values = {"clip_id": base["clips"][0]["id"], "angle_id": base["multicam_groups"][0]["angles"][1]["id"], **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                apply_action(base, "multicam_audio_lock", values, self.root)
            self.assertEqual(base, original)
        for source_in in (0, 13):
            p = copy.deepcopy(base); p["clips"][0]["in"] = source_in
            if source_in == 0:
                p["multicam_groups"][0]["angles"][0]["in"] = 48
                p["multicam_groups"][0]["audio_lock"]["clock"]["angles"][0]["in"] = 48
            with self.subTest(source_in=source_in), self.assertRaisesRegex(ValueError, "beyond its locked audio source"):
                validate_project(p, self.root)

    def test_monitor_bounds_and_locked_track_are_explicit(self):
        p = self.locked(); clip = p["clips"][0]
        for frame in (-1, 120, True, float("nan")):
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                apply_action(p, "multicam_monitor", {"clip_id": clip["id"], "frame": frame}, self.root)
        p["tracks"] = [{"id": 0, "locked": True}]
        with self.assertRaisesRegex(ValueError, "Unlock"):
            apply_action(p, "multicam_audio_lock", {"clip_id": clip["id"], "angle_id": None}, self.root)
        with self.assertRaisesRegex(ValueError, "Unlock"):
            apply_action(p, "audio_map", {"clip_id": clip["id"], "stream_index": 1}, self.root)
        unlocked = self.project(); unlocked["clips"][0].update({"in": 0, "duration": 144})
        plan = apply_action(unlocked, "multicam_monitor", {"clip_id": unlocked["clips"][0]["id"], "frame": 143}, self.root)["monitor"]
        self.assertTrue(plan["angles"][0]["available"]); self.assertFalse(plan["angles"][1]["available"])

    def test_shared_sound_edits_respect_locked_tracks_in_inactive_sequences(self):
        p = self.locked(); child_clip = copy.deepcopy(p["clips"][0]); child_clip["id"] = "inactive_camera"
        p.update(sequence_id="main", sequence_name="Main", sequences=[{"id": "child", "name": "Locked child", "clips": [child_clip], "titles": [], "tracks": [{"id": 0, "locked": True}]}])
        for action, values in (("multicam_audio_lock", {"angle_id": None}), ("audio_map", {"stream_index": 1, "channels": [0, 1]})):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "every affected camera track"):
                apply_action(p, action, {"clip_id": p["clips"][0]["id"], **values}, self.root)

    def test_replaced_camera_bytes_are_refused_by_monitor_and_export(self):
        p = self.locked()
        with tempfile.TemporaryDirectory(prefix="cinematicum-monitor-tamper-ENGINE-TEST-") as temporary:
            root = Path(temporary); (root / "media").mkdir()
            for asset in p["assets"]:
                shutil.copyfile(self.root / asset["path"], root / asset["path"])
            # A valid camera replacement keeps probing successful. The source
            # identity fence, rather than a damaged decoder, must refuse it.
            shutil.copyfile(self.root / "media/camera_a.mov", root / "media/camera_b.mov")
            # Keep the replacement's two-stream shape so validation reaches
            # the admitted source-byte check as it would after a relink.
            p["multicam_groups"][0]["audio_lock"].update(stream_index=1)
            with self.assertRaisesRegex(ValueError, "source changed"):
                apply_action(p, "multicam_monitor", {"clip_id": p["clips"][0]["id"], "frame": 0}, root)
            target = root / "output.mov"
            with self.assertRaisesRegex(ValueError, "source changed"):
                render_project(p, root, target, "prores")
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
