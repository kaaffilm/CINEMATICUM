"""Decoded-media acceptance for CINEMATICUM's timeline and audio controls.

All colors, numbers and tones in this module are ENGINE TEST SIGNALS ONLY.
"""
import array
import copy
import hashlib
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from engine import RenderCancelled, probe_media, render_project, validate_project
from waveform import extract_waveform


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class TimelineAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="cinematicum-ENGINE-TEST-AUDIO-")
        cls.root = Path(cls.temp.name)
        (cls.root / "media").mkdir()
        for name, color in (("red", "red"), ("blue", "blue")):
            cls.ffmpeg(["-f", "lavfi", "-i", f"color=c={color}:s=96x64:r=24:d=4",
                        "-f", "lavfi", "-i", "sine=f=880:r=48000:d=4",
                        "-c:v", "ffv1", "-c:a", "pcm_s16le", "-shortest", str(cls.media(name))])
        cls.ffmpeg(["-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "96x64", "-framerate", "24",
                    "-i", "pipe:0", "-c:v", "ffv1", "-pix_fmt", "gbrp", str(cls.media("counter"))],
                   b"".join(bytes([20 + n * 9, 0, 0]) * (96 * 64) for n in range(24)))
        cls.ffmpeg(["-f", "lavfi", "-i", "color=c=white:s=96x64:r=24:d=2",
                    "-vf", "drawbox=x=0:y=0:w=96:h=24:color=black:t=fill,drawbox=x=0:y=40:w=96:h=24:color=black:t=fill",
                    "-c:v", "ffv1", str(cls.media("bar"))])
        cls.ffmpeg(["-f", "lavfi", "-i", "aevalsrc=if(lt(t\\,1)\\,0\\,0.3*sin(2*PI*880*t))|if(lt(t\\,1)\\,0\\,0.15*sin(2*PI*440*t)):s=48000:d=2",
                    "-c:a", "pcm_f32le", str(cls.media("wave", "wav"))])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def media(cls, name, suffix="mkv"):
        return cls.root / "media" / f"ENGINE_TEST_ONLY_{name}.{suffix}"

    @staticmethod
    def ffmpeg(args, input_data=None):
        return subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1", "-threads", "1"] + args,
                              input=input_data, check=True, capture_output=True, timeout=40)

    def project(self, *names):
        return {"version": 1, "id": "timeline_test", "name": "ENGINE TEST SIGNALS ONLY", "fps": 24,
                "width": 96, "height": 64, "assets": [
                    {"id": n, "path": "media/" + self.media(n, "wav" if n == "wave" else "mkv").name}
                    for n in names], "clips": [], "titles": []}

    @staticmethod
    def clip(asset, ident="clip", **kw):
        return {"id": ident, "asset_id": asset, "track": 0, "start": 0, "in": 0, "duration": 24, **kw}

    def render(self, project, name):
        path = self.root / "exports" / f"ENGINE_TEST_ONLY_{name}.mov"
        render_project(project, self.root, path, "prores")
        return path

    def frames(self, path):
        raw = self.ffmpeg(["-i", str(path), "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "-threads", "1", "pipe:1"]).stdout
        return [raw[i:i + 96 * 64 * 3] for i in range(0, len(raw), 96 * 64 * 3)]

    @staticmethod
    def pixel(frame, x=48, y=32):
        offset = (y * 96 + x) * 3
        return tuple(frame[offset:offset + 3])

    def pcm(self, path):
        raw = self.ffmpeg(["-i", str(path), "-map", "0:a:0", "-ac", "2", "-ar", "48000", "-f", "f32le", "pipe:1"]).stdout
        values = array.array("f", raw)
        return values[0::2], values[1::2]

    @staticmethod
    def rms(values, start=0, duration=None):
        samples = values[round(start * 48000):None if duration is None else round((start + duration) * 48000)]
        return math.sqrt(sum(v * v for v in samples) / len(samples)) if samples else 0

    def test_retime_has_exact_output_frames_and_preserves_slow_split_boundaries(self):
        for speed in (.25, .5, 1, 2, 4):
            with self.subTest(speed=speed):
                p = self.project("counter")
                p["clips"] = [self.clip("counter", duration=int(24 / speed), speed=speed)]
                frames = self.frames(self.render(p, f"speed_{speed}"))
                self.assertEqual(len(frames), int(24 / speed))
                self.assertGreater(self.pixel(frames[-1])[0], 170, "The final stretched source frame must remain visible")
                self.assertGreater(self.pixel(frames[0])[0], 10)
                if speed == 1:
                    self.assertTrue(all(abs(self.pixel(frame)[0] - (20 + index * 9)) <= 4
                                        for index, frame in enumerate(frames)),
                                    "Container PTS rounding must not drop or duplicate normal-speed frames")
        for reverse in (False, True):
            p = self.project("counter")
            p["clips"] = [self.clip("counter", duration=48, speed=.25, reverse=reverse)]
            original = self.frames(self.render(p, f"unsplit_{reverse}"))
            left, right = copy.deepcopy(p["clips"][0]), copy.deepcopy(p["clips"][0])
            left["duration"], right["duration"], right["start"], right["id"] = 5, 43, 5, "right"
            if reverse:
                left["in"] = 43 * .25
            else:
                right["in"] = 5 * .25
            p["clips"] = [left, right]
            split = self.frames(self.render(p, f"split_{reverse}"))
            self.assertEqual([self.pixel(f)[0] for f in original], [self.pixel(f)[0] for f in split],
                             "A split at fractional source position must preserve every output frame")

    def test_reverse_picture_and_sound_and_source_bounds(self):
        p = self.project("counter")
        p["clips"] = [self.clip("counter", reverse=True)]
        frames = self.frames(self.render(p, "reverse"))
        self.assertGreater(self.pixel(frames[0])[0], self.pixel(frames[-1])[0] + 150)
        p["clips"][0].update({"speed": 4, "duration": 24})
        with self.assertRaisesRegex(ValueError, "beyond its source"):
            validate_project(p, self.root)
        p = self.project("wave")
        p["clips"] = [self.clip("wave", track=-1, duration=48, reverse=True)]
        left, right = self.pcm(self.render(p, "audio_reverse"))
        self.assertGreater(self.rms(left, .2, .2), .15)
        self.assertLess(self.rms(left, 1.5, .2), .0001)
        self.assertGreater(self.rms(left, .2, .2), self.rms(right, .2, .2) * 1.9)

    def test_audio_tempo_duration_and_pitch(self):
        for speed in (.25, .5, 2, 4):
            p = self.project("red")
            p["clips"] = [self.clip("red", duration=24, speed=speed, track=-1)]
            left, _ = self.pcm(self.render(p, f"tempo_{speed}"))
            self.assertEqual(len(left), 48000)
            signal = left[12000:24000]
            crossings = sum(a <= 0 < b for a, b in zip(signal, signal[1:]))
            self.assertLess(abs(crossings * 4 - 880), 12, "Tempo adjustment must preserve tone pitch")
            self.assertGreater(self.rms(left, .3, .2), .05)

    def test_track_mute_solo_classes_and_gain(self):
        p = self.project("red", "blue")
        p["clips"] = [self.clip("red", track=0), self.clip("blue", "blue", track=1, volume=0),
                      self.clip("red", "audio", track=-1, volume=.5)]
        p["tracks"] = [{"id": 0, "solo": True, "gain": 0}, {"id": -1, "solo": True, "gain": .5}]
        out = self.render(p, "solo_classes")
        r, g, b = self.pixel(self.frames(out)[12])
        self.assertGreater(r, b + 120, "Video solo must hide other picture tracks")
        left, _ = self.pcm(out)
        self.assertGreater(self.rms(left, .2, .2), .012, "Audio solo is independent of picture solo")
        self.assertLess(self.rms(left, .2, .2), .019, "Clip and track gains must multiply")
        p["tracks"][0]["mute"] = True
        p["tracks"][1]["mute"] = True
        out = self.render(p, "muted")
        self.assertLess(max(self.pixel(self.frames(out)[12])), 5)
        self.assertLess(self.rms(self.pcm(out)[0]), .0001)

    def test_linear_fades_and_stereo_balance_change_decoded_samples(self):
        p = self.project("red")
        p["clips"] = [self.clip("red", duration=48, audio={"fade_in": 12, "fade_out": 12, "pan": -1})]
        left, right = self.pcm(self.render(p, "fades_pan"))
        middle = self.rms(left, .8, .1)
        self.assertGreater(middle, .05)
        self.assertLess(self.rms(right), .0001, "Full left balance must silence only the right channel")
        self.assertLess(self.rms(left, .02, .05), middle * .2)
        self.assertLess(self.rms(left, 1.93, .05), middle * .2)
        p["clips"][0]["audio"] = {"pan": 1}
        left, right = self.pcm(self.render(p, "balance_right"))
        self.assertLess(self.rms(left), .0001)
        self.assertGreater(self.rms(right), .05)

    def test_independent_volume_curves_and_outgoing_easing_are_audible(self):
        measurements = {}
        for interpolation in ("constant", "ease_in", "linear", "ease_out", "ease_in_out"):
            p = self.project("red")
            p["clips"] = [self.clip("red", volume=0, keyframes=[
                {"frame": 0, "volume": 0, "interpolation": interpolation},
                {"frame": 6, "rotation": 0},
                {"frame": 20, "volume": 1}])]
            left, _ = self.pcm(self.render(p, "gain_" + interpolation))
            measurements[interpolation] = self.rms(left, .18, .04)
            self.assertGreater(self.rms(left, .9, .05), .05, "A zero base volume must not discard animated audio")
        self.assertLess(measurements["constant"], .0001)
        self.assertLess(measurements["ease_in"], measurements["ease_in_out"])
        self.assertLess(measurements["ease_in_out"], measurements["linear"])
        self.assertLess(measurements["linear"], measurements["ease_out"])

    def test_dynamic_rotation_changes_pixels_and_holds_tail(self):
        p = self.project("bar")
        p["clips"] = [self.clip("bar", keyframes=[{"frame": 0, "rotation": 0, "interpolation": "constant"},
                                                  {"frame": 12, "rotation": 90}])]
        frames = self.frames(self.render(p, "rotation"))
        self.assertGreater(min(self.pixel(frames[0], 80, 32)), 220)
        self.assertLess(max(self.pixel(frames[11], 48, 8)), 10)
        self.assertLess(max(self.pixel(frames[12], 80, 32)), 10)
        self.assertGreater(min(self.pixel(frames[12], 48, 8)), 220)
        self.assertGreater(min(self.pixel(frames[-1], 48, 8)), 220)

    def test_trims_and_splits_preserve_original_hold_eased_curves_and_fades(self):
        p = self.project("red")
        clip = self.clip("red", duration=48, scale=.5, x=-.18, opacity=.4, volume=.2,
                         animation_duration=48, animation_start=0, animation_offset=0,
                         audio={"fade_in": 12, "fade_out": 12, "fade_duration": 48, "fade_offset": 0},
                         keyframes=[{"frame": 0, "x": -.18, "opacity": .4, "volume": .2, "rotation": 0, "interpolation": "constant"},
                                    {"frame": 7, "x": .18, "opacity": 1, "volume": .85, "rotation": 90, "interpolation": "ease_in_out"},
                                    {"frame": 17, "scale": .7},
                                    {"frame": 29, "x": -.1, "opacity": .7, "volume": .4, "rotation": -30, "interpolation": "constant"},
                                    {"frame": 39, "x": .18, "opacity": 1, "volume": .9, "rotation": 0}])
        p["clips"] = [clip]
        original = self.render(p, "original_envelopes")
        pictures, channels = self.frames(original), self.pcm(original)
        self.assertNotEqual(pictures[6], pictures[7], "The hold must change exactly on the seventh frame")

        def window(start, end, timeline_start, ident):
            item = copy.deepcopy(clip)
            item.update(id=ident, start=timeline_start, duration=end-start,
                        animation_offset=start)
            item["in"] = start
            item["audio"]["fade_offset"] = start
            return item

        p["clips"] = [window(11, 43, 0, "trimmed")]
        trimmed = self.render(p, "trimmed_envelopes")
        self.assertEqual([hashlib.sha256(f).hexdigest() for f in self.frames(trimmed)],
                         [hashlib.sha256(f).hexdigest() for f in pictures[11:43]],
                         "Trimming inside an easing segment must preserve every original picture")
        for actual, expected in zip(self.pcm(trimmed), channels):
            expected = expected[11 * 2000:43 * 2000]
            self.assertEqual(len(actual), len(expected))
            self.assertLessEqual(max(abs(a-b) for a, b in zip(actual, expected)), 1/32768,
                                 "Gain automation and fades must keep their original sample envelope after trimming")

        p["clips"] = [window(0, 5, 0, "first"), window(5, 19, 5, "second"), window(19, 48, 19, "third")]
        split = self.render(p, "split_envelopes")
        self.assertEqual([hashlib.sha256(f).hexdigest() for f in self.frames(split)],
                         [hashlib.sha256(f).hexdigest() for f in pictures],
                         "Splitting must preserve original held and eased curve segments without inserting keys")
        for actual, expected in zip(self.pcm(split), channels):
            self.assertEqual(len(actual), len(expected))
            self.assertLessEqual(max(abs(a-b) for a, b in zip(actual, expected)), 1/32768,
                                 "A split must not restart its fade or refit its gain curve")

    def test_negative_animation_domain_survives_a_forward_trim_and_holds_before_first_key(self):
        p = self.project("red")
        p["clips"] = [self.clip("red", duration=12, opacity=.5, volume=.5,
                               animation_start=-6, animation_duration=24, animation_offset=-9,
                               keyframes=[{"frame": -6, "opacity": .2, "volume": .2, "interpolation": "constant"},
                                          {"frame": -2, "x": 0}, {"frame": 7, "opacity": 1, "volume": 1}])]
        out = self.render(p, "negative_animation")
        frames = self.frames(out)
        self.assertEqual(frames[0], frames[3], "Time before the first property key must hold that key")
        left, _ = self.pcm(out)
        self.assertAlmostEqual(self.rms(left, .01, .05), self.rms(left, .15, .05), delta=.0002)
        p["clips"][0].update(animation_offset=2, duration=3)
        normalized = validate_project(p, self.root)["clips"][0]
        self.assertEqual(normalized["keyframes"][0]["frame"], -6,
                         "Fixed domain bounds must preserve negative keys after a forward trim")

    def test_animation_and_fade_domains_validate_without_discarding_original_keys(self):
        p = self.project("red")
        p["clips"] = [self.clip("red", duration=5, animation_duration=48,
                               keyframes=[{"frame": 39, "volume": .5}],
                               audio={"fade_in": 12, "fade_out": 12, "fade_duration": 48, "fade_offset": 7})]
        c = validate_project(p, self.root)["clips"][0]
        self.assertEqual(c["keyframes"][0]["frame"], 39)
        self.assertEqual(c["audio"]["fade_in"], 12)
        maximum = 24 * 6 * 60 * 60
        for field, value in (("animation_start", 1), ("animation_start", -maximum-1),
                             ("animation_duration", 0), ("animation_duration", maximum+1),
                             ("animation_offset", .5), ("animation_offset", maximum+1)):
            with self.subTest(field=field, value=value):
                invalid = copy.deepcopy(p)
                invalid["clips"][0][field] = value
                with self.assertRaises(ValueError):
                    validate_project(invalid, self.root)
        for field, value in (("fade_duration", 0), ("fade_duration", maximum+1),
                             ("fade_offset", maximum+1), ("fade_offset", -.5), ("fade_in", 40)):
            with self.subTest(field=field, value=value):
                invalid = copy.deepcopy(p)
                invalid["clips"][0]["audio"][field] = value
                with self.assertRaises(ValueError):
                    validate_project(invalid, self.root)
        for frame in (-1, 48):
            invalid = copy.deepcopy(p)
            invalid["clips"][0]["keyframes"] = [{"frame": frame, "volume": .2}]
            with self.assertRaisesRegex(ValueError, "Keyframe position"):
                validate_project(invalid, self.root)

    def test_rotated_working_canvas_is_bounded_before_decode(self):
        self.ffmpeg(["-f", "lavfi", "-i", "color=c=white:s=8192x16:r=24:d=1",
                     "-c:v", "ffv1", str(self.media("ultrawide"))])
        p = self.project("ultrawide")
        p.update(width=8192, height=16)
        p["clips"] = [self.clip("ultrawide", scale=4, keyframes=[{"frame": 12, "rotation": 90}])]
        with self.assertRaisesRegex(ValueError, "working-image limit"):
            validate_project(p, self.root)

    def test_waveforms_measure_samples_cache_and_cancel(self):
        cache = self.root / "waveform-cache"
        wave = extract_waveform(self.media("wave", "wav"), cache, bins=32)
        self.assertFalse(wave["cached"])
        self.assertEqual(sum(wave["sample_counts"]), 96000)
        self.assertEqual(wave["duration"], 2)
        self.assertEqual(wave["channels"], 2)
        self.assertEqual(wave["peaks"][0]["max"][:16], [0] * 16)
        self.assertAlmostEqual(wave["peaks"][0]["max"][20], .3, places=5)
        self.assertAlmostEqual(wave["peaks"][1]["max"][20], .15, places=5)
        self.assertAlmostEqual(wave["peaks"][0]["rms"][20], .3 / math.sqrt(2), places=4)
        with patch("waveform.subprocess.Popen", side_effect=AssertionError("Cached waveform must not be re-decoded")):
            self.assertTrue(extract_waveform(self.media("wave", "wav"), cache, bins=32)["cached"])
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(RenderCancelled):
            extract_waveform(self.media("wave", "wav"), cache, bins=64, cancel_event=cancel)
        with self.assertRaisesRegex(ValueError, "no audio"):
            extract_waveform(self.media("counter"), cache)
        with self.assertRaisesRegex(ValueError, "bins"):
            extract_waveform(self.media("wave", "wav"), cache, bins=0)


if __name__ == "__main__":
    unittest.main()
