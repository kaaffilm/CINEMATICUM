"""Actual selected-stream PCM, padding, provenance, cancellation and HTTP ranges."""
import copy
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from audio_source import (CACHE_DIRECTORY, RATE, cached_source, create_source,
                          source_file, source_recipe)
from engine import probe_media
from media_management import digest_file
from server import Server, Store


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "real FFmpeg required")
class AudioSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="cinematicum-source-audio-fixture-")
        cls.movie = Path(cls.fixture.name) / "ENGINE_TEST_selected_streams.mov"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "color=c=blue:s=128x96:r=8:d=2", "-f", "lavfi", "-i",
                        "aevalsrc=0.2*sin(2*PI*220*t)|0.3*sin(2*PI*330*t):s=44100:d=1:c=stereo",
                        "-f", "lavfi", "-i",
                        "aevalsrc=0.1|0.2|0.3*sin(2*PI*440*t)|0.4|0.5|1.2*sin(2*PI*660*t):s=48000:d=1.5:c=5.1",
                        "-map", "0:v", "-map", "1:a", "-map", "2:a", "-c:v", "libx264",
                        "-threads", "1", "-c:a", "pcm_f32le", str(cls.movie)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cinematicum-source-audio-TEST-")
        self.root = Path(self.temp.name)
        (self.root / "media").mkdir()
        self.source = self.root / "media" / "source.mov"
        shutil.copyfile(self.movie, self.source)
        self.asset = {"id": "source", "path": "media/source.mov", "name": self.movie.name,
                      "sha256": digest_file(self.source), **probe_media(self.source)}
        self.project = {"assets": [self.asset]}

    def tearDown(self):
        self.temp.cleanup()

    def decode(self, path, stream_index=0, channels=None):
        filters = ["asetpts=PTS-STARTPTS", "aresample=48000"]
        if channels is not None:
            filters.append(f"pan=stereo|c0=c{channels[0]}|c1=c{channels[1]}")
        filters.append("aformat=sample_fmts=flt:channel_layouts=stereo")
        return subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path),
                                        "-map", f"0:{stream_index}", "-af", ",".join(filters),
                                        "-f", "f32le", "-c:a", "pcm_f32le", "-"])

    def test_exact_original_stream_channel_pcm_and_clock_padding(self):
        before = self.source.read_bytes()
        result = create_source(self.project, self.root, "source", 2, [5, 2])
        path, receipt = source_file(self.project, self.root, result["cache_key"])
        self.assertEqual(result["source_frames"], 72_000)
        self.assertEqual(result["frames"], 96_000)
        self.assertEqual(result["padded_frames"], 24_000)
        self.assertEqual(result["data_offset"], 58)
        self.assertEqual(result["frame_bytes"], 8)
        self.assertEqual(result["source_time_scale"], 1)
        expected = self.decode(self.source, 2, [5, 2])
        actual = self.decode(path)
        self.assertEqual(actual[:len(expected)], expected)
        self.assertEqual(actual[len(expected):], b"\0" * (24_000 * 8))
        self.assertGreater(max(struct.unpack("<" + "f" * (len(expected) // 4), expected)), 1.1)
        self.assertEqual(receipt["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue(cached_source(self.project, self.root, "source", 2, [5, 2])["cached"])
        self.assertTrue(create_source(self.project, self.root, "source", 2, [5, 2])["cached"])

    def test_default_stereo_downmix_and_selection_are_different_real_caches(self):
        first = create_source(self.project, self.root, "source")
        second = create_source(self.project, self.root, "source", 2)
        swapped = create_source(self.project, self.root, "source", 2, [5, 2])
        self.assertEqual(len({r["cache_key"] for r in (first, second, swapped)}), 3)
        for result in (first, second):
            path, _ = source_file(self.project, self.root, result["cache_key"])
            expected = self.decode(self.source, result["stream_index"])
            actual = self.decode(path)
            self.assertEqual(actual[:len(expected)], expected)
            self.assertEqual(actual[len(expected):], b"\0" * (len(actual)-len(expected)))

    def test_changed_source_or_derivative_is_not_served_as_verified(self):
        result = create_source(self.project, self.root, "source", 2, [5, 2])
        path, _ = source_file(self.project, self.root, result["cache_key"])
        with path.open("r+b") as stream:
            stream.seek(-10, 2)
            stream.write(b"changed")
        self.assertIsNone(cached_source(self.project, self.root, "source", 2, [5, 2]))
        with self.assertRaises(FileNotFoundError):
            source_file(self.project, self.root, result["cache_key"])
        create_source(self.project, self.root, "source", 2, [5, 2])
        with self.source.open("ab") as stream:
            stream.write(b"changed original")
        with self.assertRaisesRegex(ValueError, "changed"):
            cached_source(self.project, self.root, "source", 2, [5, 2])
        with self.assertRaises(FileNotFoundError):
            source_file(self.project, self.root, result["cache_key"])

    def test_pitch_preserving_tempo_is_bound_to_source_recipe(self):
        result = create_source(self.project, self.root, "source", 2, [5, 2], playback_rate=1.5)
        path, _ = source_file(self.project, self.root, result["cache_key"])
        self.assertEqual(result["frames"], 64_000)
        self.assertEqual(result["playback_rate"], 1.5)
        self.assertEqual(result["source_time_scale"], 1.5)
        expected = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(self.source),
            "-map", "0:2", "-af", "asetpts=PTS-STARTPTS,aresample=48000,pan=stereo|c0=c5|c1=c2,aformat=sample_fmts=flt:channel_layouts=stereo,atempo=1.5",
            "-c:a", "pcm_f32le", "-f", "f32le", "-"])
        actual = self.decode(path)
        self.assertEqual(actual[:len(expected)], expected)
        self.assertEqual(actual[len(expected):], b"\0" * (len(actual)-len(expected)))
        self.assertEqual(result["source_frames"], len(expected) // 8)
        import array, cmath, math
        values = array.array("f", actual)[2048:18432:2]
        amplitude = lambda frequency: 2*abs(sum(value*cmath.exp(-2j*math.pi*frequency*i/RATE) for i,value in enumerate(values)))/len(values)
        self.assertGreater(amplitude(660), 1.1)
        self.assertLess(amplitude(990), .02)
        unity = create_source(self.project, self.root, "source", 2, [5, 2])
        self.assertNotEqual(result["cache_key"], unity["cache_key"])
        self.assertIsNotNone(cached_source(self.project, self.root, "source", 2, [5, 2], 1.5))
        for speed in (0, -1, 65, True, float("nan")):
            with self.assertRaises(ValueError):
                source_recipe(self.asset, 2, [5, 2], speed)

    def test_invalid_selection_size_and_cancellation_publish_nothing(self):
        for stream, channels in ((True, None), (0, None), (2, [0, True]), (2, [0, 6]), (2, [0]), (2, "0,1")):
            with self.assertRaises(ValueError):
                source_recipe(self.asset, stream, channels)
        event = threading.Event()
        event.set()
        with self.assertRaises(Exception):
            create_source(self.project, self.root, "source", cancel_event=event)
        with patch("audio_source.MAX_CACHE_BYTES", 100):
            with self.assertRaisesRegex(ValueError, "cache"):
                create_source(self.project, self.root, "source")
        self.assertEqual(list((self.root / CACHE_DIRECTORY).glob("*.wav")), [])
        # Cancellation while the decoder is actually owned must clean its
        # temporary PCM and must not publish a partially written receipt.
        event.clear()
        def cancel(_value):
            event.set()
        with self.assertRaises(Exception):
            create_source(self.project, self.root, "source", progress=cancel, cancel_event=event)
        self.assertEqual(list((self.root / CACHE_DIRECTORY).iterdir()), [])

    def test_http_contract_dedup_ranges_and_independent_render_queue(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-source-audio-http-") as directory:
            store = Store(directory)
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            project = store.new_project({"name": "ENGINE TEST source audio"})
            incoming = Path(directory) / "selected.mov"
            shutil.copyfile(self.movie, incoming)
            asset = store.admit(project["id"], incoming, "ENGINE TEST source.mov")
            base = f"/api/projects/{project['id']}/audio-source"
            def request(method, url, body=None, token=True, headers=None):
                values = dict(headers or {})
                if token:
                    values["X-Cinematicum-Token"] = store.token
                if body is not None:
                    values["Content-Type"] = "application/json"
                    body = json.dumps(body).encode()
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
                connection.request(method, url, body, values)
                response = connection.getresponse()
                status, response_headers, data = response.status, dict(response.getheaders()), response.read()
                connection.close()
                if response_headers.get("Content-Type", "").startswith("application/json"):
                    data = json.loads(data)
                return status, response_headers, data
            release_render, release_audio = threading.Event(), threading.Event()
            real_create = create_source
            def held_create(*args, **kwargs):
                if not release_audio.wait(5):
                    raise AssertionError("The test never released source audio preparation")
                return real_create(*args, **kwargs)
            try:
                store.submit(project["id"], "render", lambda *_: release_render.wait(10))
                payload = {"asset_id": asset["id"], "stream_index": 2, "channels": [5, 2]}
                self.assertEqual(request("POST", base, payload, token=False)[0], 403)
                self.assertEqual(request("POST", base, {**payload, "path": "/unowned"})[0], 400)
                with patch("audio_source.create_source", held_create):
                    status, _, pending = request("POST", base, payload)
                    self.assertEqual(status, 202, pending)
                    status, _, duplicate = request("POST", base, payload)
                    self.assertEqual(duplicate["job"]["id"], pending["job"]["id"])
                    release_audio.set()
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline:
                        _, _, job = request("GET", "/api/jobs/" + pending["job"]["id"])
                        if job["state"] not in {"queued", "running"}:
                            break
                        time.sleep(.03)
                    self.assertEqual(job["state"], "completed", job)
                result = job["result"]
                self.assertFalse(release_render.is_set(), "audio must not wait behind a movie render")
                self.assertEqual(request("POST", base, payload)[0], 200)
                status, headers, data = request("GET", result["url"], headers={"Range": "bytes=0-63"})
                self.assertEqual(status, 206)
                self.assertEqual(len(data), 64)
                self.assertTrue(data.startswith(b"RIFF"))
                self.assertEqual(headers["Content-Range"], f"bytes 0-63/{result['byte_size']}")
                self.assertEqual(headers["ETag"], '"'+result["sha256"]+'"')
                self.assertEqual(request("GET", result["url"], headers={"Range":"bytes=58-65", "If-Match":'"'+"0"*64+'"'})[0], 412)
                self.assertEqual(request("GET", result["url"], headers={"Range":"bytes=58-65", "If-Match":'"'+result["sha256"]+'"'})[0], 206)
                status, _, data = request("GET", result["url"])
                self.assertEqual(status, 200)
                self.assertEqual(hashlib.sha256(data).hexdigest(), result["sha256"])
                self.assertEqual(list((Path(directory) / "jobs").glob(pending["job"]["id"] + ".*")), [])
                before = copy.deepcopy(store.get(project["id"]))
                self.assertEqual(before["assets"][0]["sha256"], asset["sha256"])
                self.assertEqual(before["clips"], [])
            finally:
                release_audio.set()
                release_render.set()
                server.shutdown()
                server.server_close()
                thread.join()
                store.shutdown()


if __name__ == "__main__":
    unittest.main()
