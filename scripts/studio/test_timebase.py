"""Exact clocks plus decoded-media acceptance; fixtures are ENGINE TEST SIGNALS."""
import array
import copy
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from engine import _video_timing, render_project, validate_project
from frame_preview import render_frame
from timebase import FrameRate, parse_rate, project_rate


class TimebaseTests(unittest.TestCase):
    def test_canonical_rates_decimal_labels_and_legacy_integers(self):
        for label, numerator in ((23.976, 24000), (29.97, 30000), (59.94, 60000)):
            expected = FrameRate(numerator, 1001)
            self.assertEqual(parse_rate(label), expected)
            self.assertEqual(parse_rate(numerator / 1001), expected)
            self.assertEqual(project_rate({"fps": label, "frame_rate": expected.as_dict()}), expected)
            self.assertEqual(project_rate({"frame_rate": {"numerator": numerator * 2, "denominator": 2002}}), expected)
            self.assertEqual(expected.ffmpeg, f"{numerator}/1001")
            self.assertEqual(expected.blender_fps, numerator // 1000)
            self.assertEqual(expected.blender_fps_base, 1.001)
        for fps in (1, 12, 24, 25, 30, 48, 50, 60):
            self.assertEqual(project_rate({"fps": fps}), FrameRate(fps))
            self.assertIs(type(project_rate({"fps": fps}).fps), int)
        self.assertEqual(project_rate({"fps": 30.5, "frame_rate": {"numerator": 61, "denominator": 2}}), FrameRate(61, 2))

    def test_conflicting_or_unbounded_clocks_fail_explicitly(self):
        for value in (True, None, "29.97", 0, 61, float("nan"), float("inf"), 29.9,
                      {"numerator": 30000, "denominator": 0}, {"numerator": True, "denominator": 1},
                      {"numerator": 30000, "denominator": 1001, "typo": 1},
                      {"numerator": 30000.0, "denominator": 1001},
                      {"numerator": 1000001, "denominator": 1001}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_rate(value)
        for fps in (24, 30, 23.98, True, float("nan")):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                project_rate({"fps": fps, "frame_rate": {"numerator": 24000, "denominator": 1001}})
        with self.assertRaises(ValueError):
            project_rate({"frame_rate": None})

    def test_six_hour_clock_and_sample_boundaries_do_not_accumulate_rounding(self):
        for numerator in (24000, 30000, 60000):
            rate = FrameRate(numerator, 1001)
            frames = rate.max_timeline_frames(21600)
            self.assertEqual(frames, (21600 * numerator) // 1001)
            self.assertEqual(rate.seconds_for_frames(frames), Fraction(frames * 1001, numerator))
            self.assertLessEqual(abs(Fraction(rate.samples_for_frames(frames), 48000) - rate.seconds_for_frames(frames)), Fraction(1, 96000))
            # 100,001 separately placed one-frame cuts still telescope to the
            # one exact endpoint. Multiplying a rounded frame length would fail.
            self.assertEqual(sum(rate.sample_span(i, 1) for i in range(100001)), rate.samples_for_frames(100001))
            self.assertEqual(rate.frames_for_seconds(rate.seconds_for_frames(frames)), frames)
        self.assertNotEqual(FrameRate(60000, 1001).samples_for_frames(100001),
                            100001 * FrameRate(60000, 1001).samples_for_frames(1))

    def test_conform_clock_has_exact_frame_ticks_and_bounded_avrational_components(self):
        for rate in (FrameRate(12), FrameRate(24000, 1001), FrameRate(30000, 1001),
                     FrameRate(60000, 1001), FrameRate(999983, 20000)):
            tick = Fraction(rate.conform_time_base)
            self.assertLessEqual(tick.denominator, 2 ** 31 - 1)
            self.assertEqual((rate.seconds_for_frames(1) / tick).denominator, 1)
            self.assertLessEqual(tick, Fraction(1, 10000))


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
class FractionalConformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="cinematicum-FRACTIONAL-CONFORM-")
        cls.root = Path(cls.temp.name)
        cls.rates = (FrameRate(12), FrameRate(24000, 1001), FrameRate(30000, 1001), FrameRate(60000, 1001))
        # Small lossless frames encode a unique identity in every channel.
        # Matroska rounds input PTS to milliseconds; MOV retains exact cadence.
        raw = b"".join(bytes([n * 3, n * 7 % 256, n * 11 % 256]) * 256 for n in range(60))
        for index, rate in enumerate(cls.rates):
            for extension, codec in (("mkv", "ffv1"), ("mov", "qtrle")):
                cls.ffmpeg(["-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "16x16",
                    "-framerate", rate.ffmpeg, "-i", "pipe:0", "-c:v", codec,
                    str(cls.root / f"source_{index}.{extension}")], raw)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def ffmpeg(args, data=None):
        return subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y",
            "-threads", "1", "-filter_threads", "1"] + args, input=data,
            capture_output=True, check=True, timeout=20).stdout

    def test_half_frame_source_cuts_keep_all_decoded_frames_at_integer_and_rational_rates(self):
        for index, rate in enumerate(self.rates):
            for extension in ("mkv", "mov"):
                source = self.root / f"source_{index}.{extension}"

                def decode(clip):
                    raw = self.ffmpeg(["-i", str(source), "-vf", ",".join(_video_timing(clip, rate)),
                        "-an", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"])
                    return [raw[n:n + 768] for n in range(0, len(raw), 768)]

                for speed in (.5, 1, 1.5):
                    for reverse in (False, True):
                        with self.subTest(rate=rate.ffmpeg, container=extension, speed=speed, reverse=reverse):
                            clip = {"in": .5, "duration": 10, "speed": speed, "reverse": reverse}
                            whole = decode(clip)
                            self.assertEqual(len(whole), 10)
                            for cut in (1, 3, 8):
                                left, right = {**clip, "duration": cut}, {**clip, "duration": 10 - cut}
                                if reverse:
                                    left["in"] += (10 - cut) * speed
                                else:
                                    right["in"] += cut * speed
                                self.assertEqual(decode(left) + decode(right), whole,
                                    f"Fractional source cut at {cut} must preserve every decoded frame")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class RationalMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="cinematicum-ENGINE-TEST-RATIONAL-")
        cls.root = Path(cls.temp.name)
        (cls.root / "media").mkdir()
        # MOV's rational video time base avoids reducing source timestamps to
        # Matroska milliseconds; each fixture contains 90 distinct source frames.
        raw = b"".join(bytes([20 + n * 2, 20, 40]) * (96 * 64) for n in range(90))
        for numerator in (24000, 30000, 60000):
            rate = FrameRate(numerator, 1001)
            cls.ffmpeg(["-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "96x64",
                        "-framerate", rate.ffmpeg, "-i", "pipe:0", "-f", "lavfi", "-i",
                        "aevalsrc=0.2*sin(2*PI*887*t)|0.15*sin(2*PI*443*t):s=48000:d=5",
                        "-frames:v", "90", "-t", rate.seconds_decimal(90), "-c:v", "qtrle",
                        "-c:a", "pcm_s16le", str(cls.source(numerator))], raw)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def source(cls, numerator):
        return cls.root / "media" / f"ENGINE_TEST_ONLY_{numerator}.mov"

    @staticmethod
    def ffmpeg(args, data=None):
        return subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y",
                               "-filter_complex_threads", "1", "-threads", "1"] + args,
                              input=data, capture_output=True, check=True, timeout=45).stdout

    def project(self, numerator, *, duration=47, start=0):
        rate = FrameRate(numerator, 1001)
        return {"version": 1, "id": "rational_test", "name": "ENGINE TEST SIGNALS ONLY",
                "fps": rate.fps, "frame_rate": rate.as_dict(), "width": 96, "height": 64,
                "assets": [{"id": "source", "path": "media/" + self.source(numerator).name}],
                "clips": [{"id": "clip", "asset_id": "source", "track": 0, "start": start,
                           "in": 0, "duration": duration}], "titles": []}

    def render(self, project, name, profile="prores"):
        output = self.root / (name + (".mov" if profile == "prores" else ".mp4"))
        report = render_project(project, self.root, output, profile)
        self.assertEqual(report["frame_rate"], project["frame_rate"])
        return output

    def probe(self, path):
        result = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_streams", "-show_packets", "-of", "json", str(path)],
                                capture_output=True, check=True, timeout=20)
        return json.loads(result.stdout)

    def frames(self, path):
        raw = self.ffmpeg(["-i", str(path), "-map", "0:v:0", "-pix_fmt", "rgb24", "-threads", "1", "-f", "rawvideo", "pipe:1"])
        size = 96 * 64 * 3
        return [raw[i:i+size] for i in range(0, len(raw), size)]

    def pcm(self, path):
        return array.array("h", self.ffmpeg(["-i", str(path), "-map", "0:a:0", "-ac", "2", "-ar", "48000", "-f", "s16le", "pipe:1"]))

    def test_three_broadcast_rates_have_exact_pts_frame_counts_and_pcm_duration(self):
        for numerator in (24000, 30000, 60000):
            for profile in ("prores", "h264"):
                with self.subTest(numerator=numerator, profile=profile):
                    p = self.project(numerator)
                    rate = project_rate(p)
                    output = self.render(p, f"cadence_{numerator}_{profile}", profile)
                    data = self.probe(output)
                    video = next(s for s in data["streams"] if s["codec_type"] == "video")
                    self.assertEqual(Fraction(video["avg_frame_rate"]), rate.fraction)
                    self.assertEqual(Fraction(video["r_frame_rate"]), rate.fraction)
                    self.assertEqual(int(video["nb_frames"]), 47)
                    tick = Fraction(video["time_base"])
                    pts = sorted(int(p["pts"]) * tick for p in data["packets"] if p["stream_index"] == video["index"])
                    self.assertEqual(pts, [rate.seconds_for_frames(n) for n in range(47)])
                    audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
                    sample_error = abs(Fraction(int(audio["duration_ts"])) * Fraction(audio["time_base"]) * 48000 - rate.samples_for_frames(47))
                    self.assertLessEqual(sample_error, 1)
                    if profile == "prores":
                        self.assertEqual(len(self.pcm(output)) // 2, rate.samples_for_frames(47))

    def test_rational_split_keeps_every_picture_sample_and_envelope(self):
        rate = FrameRate(30000, 1001)
        for start in (0, 1):
            for reverse in (False, True):
                with self.subTest(start=start, reverse=reverse):
                    p = self.project(30000, start=start)
                    clip = p["clips"][0]
                    clip.update(reverse=reverse, animation_duration=47, animation_offset=0,
                                scale=.7, volume=.3, audio={"fade_in": 9, "fade_out": 12, "fade_duration": 47},
                                keyframes=[{"frame": 0, "x": -.1, "volume": .3, "interpolation": "constant"},
                                           {"frame": 7, "x": .1, "volume": .9, "interpolation": "ease_in_out"},
                                           {"frame": 31, "x": -.1, "volume": .5}])
                    original = self.render(p, f"whole_{start}_{reverse}")
                    cuts = [0, 1, 2, 6, 11, 24, 47]
                    split = []
                    for index, (left, right) in enumerate(zip(cuts, cuts[1:])):
                        item = copy.deepcopy(clip)
                        item.update(id=f"part{index}", start=start + left, duration=right-left,
                                    animation_offset=left)
                        item["in"] = 47 - right if reverse else left
                        item["audio"]["fade_offset"] = left
                        split.append(item)
                    p["clips"] = split
                    cut = self.render(p, f"split_{start}_{reverse}")
                    self.assertEqual(self.frames(cut), self.frames(original), "A rational cut must preserve every picture")
                    actual, expected = self.pcm(cut), self.pcm(original)
                    self.assertEqual(len(actual), 2 * rate.samples_for_frames(start + 47))
                    self.assertEqual(len(actual), len(expected))
                    self.assertLessEqual(max(abs(a-b) for a, b in zip(actual, expected)), 1,
                                         "Cuts must preserve source samples and held/eased/faded gain on the absolute sample grid")

    def test_rational_trim_preview_and_source_retime_boundaries(self):
        p = self.project(60000, duration=60)
        clip = p["clips"][0]
        clip.update(speed=.5, scale=.5, animation_duration=60,
                    keyframes=[{"frame": 0, "x": -.15, "interpolation": "constant"},
                               {"frame": 11, "x": .15, "interpolation": "ease_in_out"},
                               {"frame": 49, "x": -.15}])
        whole = self.frames(self.render(p, "slow_whole"))
        clip.update(start=0, duration=31, **{"in": 7 * .5}, animation_offset=7)
        trimmed = self.render(p, "slow_trim")
        self.assertEqual(self.frames(trimmed), whole[7:38])
        preview = self.root / "frame.png"
        render_frame(p, self.root, 4, preview)
        raw_preview = self.frames(preview)[0]
        movie_frame = self.frames(trimmed)[4]
        # Delivery uses 4:2:2 ProRes while PNG is RGB; inspect a flat central
        # patch, not a chroma-subsampled edge, to compare shared timing/effects.
        for x, y in ((48, 32), (8, 8)):
            offset = (y * 96 + x) * 3
            self.assertLessEqual(max(abs(a-b) for a, b in zip(raw_preview[offset:offset+3], movie_frame[offset:offset+3])), 5)

    def test_default_durations_and_six_hour_bounds_are_integer_frames(self):
        p = self.project(24000)
        del p["clips"][0]["duration"]
        normalized = validate_project(p, self.root)
        self.assertEqual(normalized["clips"][0]["duration"], 24)
        self.assertEqual(normalized["frame_rate"], {"numerator": 24000, "denominator": 1001})
        self.assertEqual(project_rate(normalized), FrameRate(24000, 1001))

    def test_extended_animation_domains_preserve_keys_and_original_fade_endpoints(self):
        p = self.project(30000, duration=12)
        clip = p["clips"][0]
        keys = [{"frame": 0, "x": .1, "interpolation": "constant"},
                {"frame": 5, "x": .2, "interpolation": "linear"}]
        clip.update(animation_duration=6, keyframes=keys,
                    audio={"fade_duration": 6, "fade_offset": 0, "fade_out": 2})
        tail = validate_project(p, self.root)["clips"][0]
        self.assertEqual(tail["animation_duration"], 12)
        self.assertEqual(tail["keyframes"], keys)
        self.assertEqual((tail["audio"]["fade_duration"], tail["audio"]["fade_offset"]), (6, 0))
        clip["animation_offset"] = -3
        head = validate_project(p, self.root)["clips"][0]
        self.assertEqual((head["animation_start"], head["animation_duration"]), (-3, 9))
        self.assertEqual(head["keyframes"], keys)
        self.assertEqual((head["audio"]["fade_duration"], head["audio"]["fade_offset"]), (6, 0))
        maximum = project_rate(p).max_timeline_frames(21600)
        clip["animation_offset"] = maximum
        with self.assertRaisesRegex(ValueError, "Animation duration"):
            validate_project(p, self.root)

    def test_measured_motion_has_no_implicit_zero_in_negative_or_late_key_domains(self):
        for name, offset, keys, expected_keys in (
            ("negative", -4, [{"frame": -6, "x": .25, "y": 0}, {"frame": 6, "x": .125, "y": 0}],
             [{"frame": -6, "x": .125}, {"frame": 0, "x": .09375}, {"frame": 6, "x": .0625}]),
            ("late_reference", 0, [{"frame": 4, "x": .25, "y": 0}, {"frame": 10, "x": .125, "y": 0}],
             [{"frame": 0, "x": .125}, {"frame": 4, "x": .125}, {"frame": 10, "x": .0625}]),
        ):
            with self.subTest(domain=name):
                p = self.project(30000, duration=12)
                clip = p["clips"][0]
                clip.update(scale=.5, animation_start=-6, animation_duration=24, animation_offset=offset,
                            tracking={"version": 1, "mode": "stabilize", "keys": keys})
                measured = self.frames(self.render(p, "motion_" + name))
                del clip["tracking"]
                clip["keyframes"] = expected_keys
                expected = self.frames(self.render(p, "manual_" + name))
                self.assertEqual(measured, expected,
                                 "Measured points must interpolate/clamp their actual keys without inserting a zero at frame0")


if __name__ == "__main__":
    unittest.main()
