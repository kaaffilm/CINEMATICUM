"""Real loopback proxy tests; no Docker or editor mock is claimed as GUI proof."""
import base64
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock

from server import Store, Server


class DisplayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.headers.get("Upgrade", "").lower() == "websocket":
            key = self.headers["Sec-WebSocket-Key"]
            accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.end_headers()
            packet = self.rfile.read(6)
            self.wfile.write(packet)
            self.wfile.flush()
            self.close_connection = True
        else:
            data = b"ACTUAL-UPSTREAM-RESOURCE"
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)


class NativeHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.project = self.store.new_project({"name": "ENGINE_TEST_native_proxy"})
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), DisplayHandler)
        self.upstream.daemon_threads = True
        self.server = Server(0, self.store)
        self.threads = []
        for server in (self.upstream, self.server):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)
        self.store.native.access = Mock(return_value={"port": self.upstream.server_port, "password": "secret-not-for-jobs"})

    def tearDown(self):
        for server in (self.upstream, self.server):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join()
        self.store.shutdown()
        self.tmp.cleanup()

    def request(self, method, path, payload=None, token=False, origin=None):
        headers = {}
        if token:
            headers["X-Cinematicum-Token"] = self.store.token
        if origin:
            headers["Origin"] = origin
        if payload is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(payload)
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        client.request(method, path, payload, headers)
        response = client.getresponse()
        status, data, response_headers = response.status, response.read(), dict(response.getheaders())
        client.close()
        return status, data, response_headers

    def viewer(self):
        status, data, _ = self.request("POST", "/api/projects/" + self.project["id"] + "/native/access", {}, True)
        self.assertEqual(status, 200, data)
        return json.loads(data)["viewer_url"]

    def test_access_requires_token_and_nonce_is_not_in_project_or_jobs(self):
        path = "/api/projects/" + self.project["id"] + "/native/access"
        self.assertEqual(self.request("POST", path, {})[0], 403)
        viewer = self.viewer()
        self.assertIn("secret-not-for-jobs", viewer)
        for file in Path(self.tmp.name).rglob("*.json"):
            self.assertNotIn("secret-not-for-jobs", file.read_text())
        self.assertEqual(self.request("GET", "/native/unknown/index.html")[0], 403)

    def test_http_streams_owned_resource_and_rejects_foreign_origin(self):
        viewer = self.viewer()
        status, data, headers = self.request("GET", viewer)
        self.assertEqual((status, data), (200, b"ACTUAL-UPSTREAM-RESOURCE"))
        self.assertEqual(headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(self.request("GET", viewer, origin="https://foreign.invalid")[0], 403)
        self.assertEqual(self.request("GET", "/native/not-owned/http://example.invalid/")[0], 403)

    def test_websocket_upgrades_and_relays_real_socket_bytes(self):
        viewer = self.viewer().split("?", 1)[0]
        connection = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=5)
        key = base64.b64encode(b"abcdefghijklmnop").decode()
        request = ("GET %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
                   "Origin: http://127.0.0.1:%d\r\nUpgrade: websocket\r\n"
                   "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                   "Sec-WebSocket-Key: %s\r\n\r\n") % (viewer, self.server.server_port, self.server.server_port, key)
        connection.sendall(request.encode())
        header = b""
        while b"\r\n\r\n" not in header:
            header += connection.recv(1)
        self.assertTrue(header.startswith(b"HTTP/1.1 101"), header)
        # A masked empty binary WebSocket frame is six bytes. The bridge must
        # transmit it unchanged, without interpreting editor protocol contents.
        packet = b"\x82\x80test"
        connection.sendall(packet)
        result = b""
        while len(result) < len(packet):
            result += connection.recv(len(packet) - len(result))
        connection.close()
        self.assertEqual(packet, result)

    def test_native_export_cannot_follow_symlink_into_host_files(self):
        root = Path(self.tmp.name) / "nativeprojects" / self.project["id"] / "exports"
        root.mkdir(parents=True)
        secret = Path(self.tmp.name) / "host-secret.mp4"
        secret.write_bytes(b"unrelated file")
        (root / "escape.mp4").symlink_to(secret)
        response = self.store.native_exports(self.project["id"])
        self.assertEqual(response["imported"], [])
        self.assertEqual(secret.read_bytes(), b"unrelated file")


if __name__ == "__main__":
    unittest.main()
