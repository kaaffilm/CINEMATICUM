"""Exact source-tail regression using actual decoded 80-frame test footage."""
from __future__ import annotations

import copy
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from engine import probe_media, render_project, validate_project
from test_trim_edits import evaluate, timeline
from test_trim_ui_macos import create_fixture, decode_oracle, WIDTH, HEIGHT


class ProbeClockTests(unittest.TestCase):
    def metadata(self):
        return {
            "streams": [
                {"index": 0, "codec_type": "video", "codec_name": "h264",
                 "width": 128, "height": 96, "avg_frame_rate": "24/1",
                 "duration_ts": 40960, "time_base": "1/12288", "duration": "3.333333"},
                {"index": 1, "codec_type": "audio", "codec_name": "aac",
                 "sample_rate": "48000", "channels": 2,
                 "duration_ts": "160001", "time_base": "1/48000", "duration": "3.333354"},
            ],
            "format": {"duration": "3.334000"},
        }

    def probe_response(self, data):
        with tempfile.TemporaryDirectory(prefix="cinematicum-probe-clock-ENGINE-TEST-") as temp:
            path = Path(temp) / "ENGINE_TEST_probe_metadata.mp4"
            path.write_bytes(b"ENGINE TEST mocked ffprobe response only")
            response = subprocess.CompletedProcess([], 0, json.dumps(data), "")
            with patch("engine._executable", return_value="ffprobe"), patch("engine.subprocess.run", return_value=response):
                return probe_media(path)

    def test_primary_and_audio_use_their_own_rational_duration(self):
        result = self.probe_response(self.metadata())
        self.assertEqual(result["duration"], 80 / 24)
        self.assertEqual(result["duration"] * 24, 80)
        self.assertEqual(result["audio_duration"], 160001 / 48000)
        # Audio-only sources must use the same precision for their primary clock.
        data = self.metadata()
        data["streams"] = data["streams"][1:]
        audio = self.probe_response(data)
        self.assertEqual(audio["duration"], 160001 / 48000)
        self.assertEqual(audio["duration"], audio["audio_duration"])

    def test_invalid_tick_clock_keeps_decimal_stream_fallback(self):
        for ticks, base in ((None, "1/24"), ("N/A", "1/24"), (0, "1/24"),
                            (-1, "1/24"), (True, "1/24"), (1.5, "1/24"),
                            (2 ** 63, "1/24"), (80, None), (80, "N/A"),
                            (80, "1/0"), (80, "0/1"), (80, "-1/24"),
                            (80, "1/2147483648"), (80, "2147483648/1")):
            with self.subTest(ticks=ticks, base=base):
                data = self.metadata()
                for stream in data["streams"]:
                    stream.update(duration_ts=ticks, time_base=base)
                result = self.probe_response(data)
                self.assertEqual(result["duration"], 3.333333)
                self.assertEqual(result["audio_duration"], 3.333354)

    def test_missing_tick_and_decimal_duration_keep_tag_then_container_fallback(self):
        data = self.metadata()
        for stream in data["streams"]:
            stream.pop("duration_ts")
            stream.pop("duration")
            stream["tags"] = {"DURATION": "00:00:03.333333333"}
        tagged = self.probe_response(data)
        self.assertEqual(tagged["duration"], 3.333333333)
        self.assertEqual(tagged["audio_duration"], 3.333333333)
        for stream in data["streams"]:
            stream.pop("tags")
        container = self.probe_response(data)
        self.assertEqual(container["duration"], 3.334)
        self.assertEqual(container["audio_duration"], 3.334)


@unittest.skipUnless(shutil.which("node") and shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "Node and FFmpeg are required for the decoded trim regression")
class DecodedSourceTailTests(unittest.TestCase):
    def test_actual_80_frame_source_can_slip_to_its_last_eight_frames(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-source-tail-ENGINE-TEST-") as temp:
            root = Path(temp)
            (root / "media").mkdir()
            source = root / "media/ENGINE_TEST_80_moving_frames.mp4"
            create_fixture(source)
            raw = json.loads(subprocess.run([
                shutil.which("ffprobe"), "-v", "error", "-show_streams", "-of", "json", str(source)
            ], capture_output=True, text=True, check=True, timeout=10).stdout)["streams"][0]
            self.assertEqual(int(raw["nb_frames"]), 80)
            self.assertEqual(int(raw["duration_ts"]) * Fraction(raw["time_base"]), Fraction(80, 24))
            metadata = probe_media(source)
            self.assertEqual(metadata["duration"], 80 / 24)

            project = timeline()
            project.update(width=WIDTH, height=HEIGHT)
            project["assets"] = [{**metadata, "id": "source", "path": "media/" + source.name,
                                  "name": "ENGINE TEST exact 80-frame source"}]
            for clip in project["clips"]:
                clip["keyframes"] = []
            original = copy.deepcopy(project)
            result = evaluate(project, "slip", 999)
            self.assertEqual(result["result"]["delta"], 48)
            self.assertTrue(result["result"]["limited"])
            self.assertEqual(result["project"]["clips"][1]["in"], 72)
            self.assertEqual(project, original)

            edited = validate_project(result["project"], root)
            output = root / "exports/ENGINE_TEST_last_source_frame.mp4"
            report = render_project(edited, root, output, "preview")
            self.assertEqual(report["frames"], 24)
            expected = list(range(8, 16)) + list(range(72, 80)) + list(range(40, 48))
            oracle = decode_oracle(output, expected)
            self.assertTrue(oracle["exact_frame_order"], oracle)
            self.assertTrue(oracle["actual_motion_matches"], oracle)
            self.assertEqual(oracle["source_frames"][15], 79)


if __name__ == "__main__":
    unittest.main()
