"""Real Chromium regression for downloads registered after the script returns.

The page downloads independent known bytes from an owned loopback server. Its
second click is scheduled only after the first saved file is complete, and after
the acceptance JavaScript has returned its expected count. No media engine or
browser event is mocked. The whole-build runner rejects missing-runtime skips.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit


HERE = Path(__file__).resolve().parent
ADAPTERS = ("test_retime_browser.cjs", "test_otio_compositions_browser.cjs",
            "test_multicam_sync_browser.cjs")
FIRST = b"ENGINE TEST first download\x00\x01\xff\n" * 257
SECOND = b"ENGINE TEST late second download\x02\x80\xfe\n" * 263


class DownloadCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        configured = os.environ.get("CINEMATICUM_BROWSER")
        if not cls.node or not configured:
            raise unittest.SkipTest(
                "Actual Node, Playwright and CINEMATICUM_BROWSER are required "
                "for delayed-download acceptance"
            )
        cls.browser = Path(configured)
        if not cls.browser.is_absolute() or not cls.browser.is_file():
            raise RuntimeError("The explicitly configured browser does not exist: " + configured)

    def run_helper(self, adapter, *, second_download, timeout):
        temporary = tempfile.TemporaryDirectory(prefix="ENGINE_TEST_retime_download_")
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name).resolve()
        downloads = directory / "downloads"
        downloads.mkdir()
        events = []
        events_lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, data, content_type, filename=None):
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                if filename is not None:
                    self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    # The deliberate missing-download case closes its own page.
                    pass

            def do_GET(self):
                route = urlsplit(self.path).path
                if route in ("/first.bin", "/second.bin", "/returning"):
                    with events_lock:
                        events.append({"route": route, "monotonic": time.monotonic()})
                if route == "/":
                    self.respond(
                        b'<!doctype html><title>ENGINE TEST delayed downloads</title>'
                        b'<link rel="icon" href="data:,">'
                        b'<a id="first" href="/first.bin" download="first.bin">First</a>'
                        b'<a id="second" href="/second.bin" download="second.bin">Second</a>',
                        "text/html; charset=utf-8",
                    )
                elif route in ("/first.bin", "/second.bin"):
                    self.respond(FIRST if route == "/first.bin" else SECOND,
                                 "application/octet-stream", route[1:])
                elif route == "/first-ready":
                    try:
                        ready = (downloads / "first.bin").read_bytes() == FIRST
                    except OSError:
                        ready = False
                    self.respond(json.dumps({"ready": ready}).encode(), "application/json")
                elif route == "/returning":
                    self.respond(b"{}", "application/json")
                else:
                    self.send_error(404)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever,
                                  kwargs={"poll_interval": .025}, daemon=True)
        thread.start()
        script = directory / "download-contract.js"
        script.write_text("""
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
document.querySelector('#first').click();
const readyDeadline = performance.now() + 1700;
for (;;) {
  const response = await fetch('/first-ready', {cache: 'no-store'});
  if ((await response.json()).ready) break;
  if (performance.now() > readyDeadline) throw Error('First actual file did not finish');
  await sleep(15);
}
// The server has independently read the complete first saved attachment.
await sleep(60);
await fetch('/returning', {cache: 'no-store'});
""" + ("setTimeout(() => document.querySelector('#second').click(), 200);\n"
       if second_download else "") + """
return {passed: true, expect_download: true, expected_download_count: 2,
        first_file_verified_before_result: true};
""", encoding="utf-8")
        command = [self.node, str(HERE / adapter), "--helper",
                   "--browser", str(self.browser),
                   "--url", "http://127.0.0.1:" + str(server.server_port) + "/",
                   "--output", str(directory / "browser.png"),
                   "--script", str(script), "--download-dir", str(downloads),
                   "--timeout", str(timeout)]
        started = time.monotonic()
        process = None
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True,
                                       start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=timeout + 2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    stdout, stderr = process.communicate(timeout=.75)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout, stderr = process.communicate(timeout=.75)
                self.fail("Browser helper exceeded its bounded deadline:\n" + stdout + stderr)
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=.75)
            server.shutdown()
            server.server_close()
            thread.join(timeout=.5)
        elapsed = time.monotonic() - started
        self.assertFalse(thread.is_alive(), "Owned loopback server did not stop")
        try:
            report = json.loads(stdout)
        except (TypeError, ValueError):
            self.fail("Browser helper returned no complete JSON receipt:\n" + stdout + stderr)
        details = json.dumps({"adapter": adapter, "exit_code": process.returncode, "elapsed_seconds": elapsed,
                              "events": events, "report": report, "stderr": stderr}, indent=2)
        self.assertFalse(report.get("native_certified"), details)
        self.assertFalse(report.get("page_errors"), details)
        return directory, downloads, report, process.returncode, elapsed, events, details

    def test_late_second_registration_waits_for_both_actual_files(self):
        for adapter in ADAPTERS:
            with self.subTest(adapter=adapter):
                self.assert_late_download(adapter)

    def assert_late_download(self, adapter):
        directory, downloads, report, status, elapsed, events, details = self.run_helper(
            adapter, second_download=True, timeout=5)
        self.assertEqual(status, 0, details)
        self.assertIs(report.get("passed"), True, details)
        self.assertEqual(report.get("expected_download_count"), 2, details)
        self.assertIs(report.get("first_file_verified_before_result"), True, details)
        self.assertFalse(report.get("download_errors"), details)
        rows = report.get("downloads", [])
        self.assertEqual(len(rows), 2, details)
        self.assertEqual({row.get("suggested_filename") for row in rows},
                         {"first.bin", "second.bin"}, details)
        for row in rows:
            self.assertEqual(row.get("state"), "completed", details)
            self.assertEqual(Path(row["path"]).resolve(),
                             downloads / row["suggested_filename"], details)
        self.assertEqual((downloads / "first.bin").read_bytes(), FIRST, details)
        self.assertEqual((downloads / "second.bin").read_bytes(), SECOND, details)
        self.assertEqual({p.name for p in downloads.iterdir()}, {"first.bin", "second.bin"}, details)
        self.assertGreater((directory / "browser.png").stat().st_size, 100, details)
        self.assertEqual([event["route"] for event in events],
                         ["/first.bin", "/returning", "/second.bin"], details)
        # The second registration cannot belong to the pre-return promise list:
        # its click runs in a later timer task, after the JS result has resolved.
        self.assertGreaterEqual(events[2]["monotonic"] - events[1]["monotonic"], .15, details)
        self.assertLess(elapsed, 7, details)

    def test_missing_second_download_fails_under_three_second_deadline(self):
        for adapter in ADAPTERS:
            with self.subTest(adapter=adapter):
                self.assert_missing_download(adapter)

    def assert_missing_download(self, adapter):
        _, downloads, report, status, elapsed, events, details = self.run_helper(
            adapter, second_download=False, timeout=3)
        self.assertNotEqual(status, 0, details)
        self.assertIs(report.get("passed"), False, details)
        self.assertEqual((downloads / "first.bin").read_bytes(), FIRST, details)
        self.assertFalse((downloads / "second.bin").exists(), details)
        self.assertEqual([event["route"] for event in events],
                         ["/first.bin", "/returning"], details)
        rows = report.get("downloads", [])
        self.assertEqual(len(rows), 1, details)
        self.assertEqual(rows[0].get("suggested_filename"), "first.bin", details)
        self.assertEqual(rows[0].get("state"), "completed", details)
        reason = str(report.get("error") or report.get("download_error") or report.get("download_errors"))
        self.assertRegex(reason.lower(), r"download|deadline|time limit|timed out", details)
        self.assertLess(elapsed, 5, details)


if __name__ == "__main__":
    unittest.main()
