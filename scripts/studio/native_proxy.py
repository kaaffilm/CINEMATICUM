"""Same-origin HTTP/WebSocket bridge to an app-owned, authenticated Xpra port.

The caller validates Host/Origin and resolves an unguessable project session
route. This module never accepts a destination host or port from an HTTP client.
"""
from __future__ import annotations

import http.client
import select
import socket
import time
from urllib.parse import urlsplit


def validate_target(port, path):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid owned runtime port")
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid native workspace resource")
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise ValueError("Invalid native workspace resource")
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc:
        raise ValueError("Invalid native workspace resource")


def proxy_http(handler, port, path, prefix):
    validate_target(port, path)
    if handler.command not in {"GET", "HEAD"}:
        raise PermissionError("Native resources only accept GET and HEAD")
    headers = {"Host": "127.0.0.1:%d" % port, "Connection": "close"}
    for name in ("Accept", "Accept-Encoding", "Range", "If-None-Match", "If-Modified-Since"):
        if handler.headers.get(name):
            headers[name] = handler.headers[name]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        connection.request(handler.command, path, headers=headers)
        response = connection.getresponse()
        handler.send_response(response.status)
        for name in ("Content-Type", "Content-Length", "Content-Encoding", "Content-Range", "Accept-Ranges", "ETag", "Last-Modified"):
            value = response.getheader(name)
            if value is not None:
                handler.send_header(name, value)
        location = response.getheader("Location")
        if location:
            # No redirect out of the authenticated app-owned resource subtree.
            target = urlsplit(location)
            if target.scheme or target.netloc or location.startswith("//"):
                raise PermissionError("Native workspace returned an external redirect")
            handler.send_header("Location", prefix + location.lstrip("/"))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Referrer-Policy", "no-referrer")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "SAMEORIGIN")
        # Xpra's own client needs inline initialization, WASM and worker blobs.
        # This policy is scoped to /native/<nonce>/, not the main app or API.
        handler.send_header("Content-Security-Policy", "default-src 'self' blob: data:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.close_connection = True
        if handler.command != "HEAD":
            while True:
                data = response.read(65536)
                if not data:
                    break
                handler.wfile.write(data)
    finally:
        connection.close()


def proxy_websocket(handler, port, path, closing):
    validate_target(port, path)
    if handler.command != "GET" or handler.headers.get("Upgrade", "").lower() != "websocket":
        raise ValueError("Expected WebSocket upgrade")
    if not handler.headers.get("Sec-WebSocket-Key") or handler.headers.get("Sec-WebSocket-Version") != "13":
        raise ValueError("Unsupported WebSocket handshake")
    upstream = socket.create_connection(("127.0.0.1", port), timeout=10)
    try:
        headers = ["GET %s HTTP/1.1" % path, "Host: 127.0.0.1:%d" % port,
                   "Upgrade: websocket", "Connection: Upgrade",
                   "Origin: http://127.0.0.1:%d" % port]
        for name in ("Sec-WebSocket-Key", "Sec-WebSocket-Version", "Sec-WebSocket-Protocol", "Sec-WebSocket-Extensions"):
            value = handler.headers.get(name)
            if value:
                if "\r" in value or "\n" in value:
                    raise ValueError("Invalid WebSocket header")
                headers.append(name + ": " + value)
        upstream.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("latin1"))
        handshake = bytearray()
        while b"\r\n\r\n" not in handshake:
            part = upstream.recv(4096)
            if not part:
                raise ConnectionError("Native display closed during connection")
            handshake.extend(part)
            if len(handshake) > 65536:
                raise ConnectionError("Native display returned an invalid handshake")
        first = bytes(handshake).split(b"\r\n", 1)[0]
        if not first.startswith((b"HTTP/1.1 101 ", b"HTTP/1.0 101 ")):
            raise ConnectionError("Native display refused its WebSocket connection")
        # Preserve any first protocol frame already read after the headers.
        handler.wfile.write(handshake)
        handler.wfile.flush()
        handler.close_connection = True
        downstream = handler.connection
        downstream.settimeout(10)
        upstream.settimeout(10)
        last_activity = time.monotonic()
        while not closing():
            ready, _, _ = select.select([downstream, upstream], [], [], 1)
            if not ready:
                if time.monotonic() - last_activity > 180:
                    return
                continue
            for source in ready:
                data = source.recv(65536)
                if not data:
                    return
                (upstream if source is downstream else downstream).sendall(data)
                last_activity = time.monotonic()
    finally:
        upstream.close()
