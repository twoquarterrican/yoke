"""A minimal DevTools WebSocket client for one page; host stdlib only.

Shipped to the test machine ahead of ``linux_desktop_chromium``, which has no
WebSocket library there, so it carries no __future__ import.
"""

import base64
import json
import os
import socket
import struct
from urllib.parse import urlsplit


class DevToolsPage:
    """A minimal client for one page's DevTools WebSocket."""

    def __init__(self, url):
        parts = urlsplit(url)
        self.socket = socket.create_connection((parts.hostname, parts.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall(
            f"GET {parts.path} HTTP/1.1\r\nHost: {parts.netloc}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        self.buffer = b""
        head = self._read_until(b"\r\n\r\n")
        if not head.startswith(b"HTTP/1.1 101"):
            raise OSError("DevTools refused the page connection")
        self.request_id = 0

    def _read_until(self, marker):
        while marker not in self.buffer:
            self._receive()
        head, _, self.buffer = self.buffer.partition(marker)
        return head

    def _receive(self):
        chunk = self.socket.recv(65536)
        if not chunk:
            raise OSError("DevTools closed the page connection")
        self.buffer += chunk

    def _read(self, size):
        while len(self.buffer) < size:
            self._receive()
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def _send(self, body):
        size = len(body)
        header = bytes([0x81])
        if size < 126:
            header += bytes([0x80 | size])
        elif size < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", size)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", size)
        mask = os.urandom(4)
        self.socket.sendall(
            header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(body))
        )

    def call(self, method, **params):
        self.request_id += 1
        self._send(
            json.dumps(
                {"id": self.request_id, "method": method, "params": params}
            ).encode()
        )
        message = b""
        while True:
            first, second = self._read(2)
            size = second & 0x7F
            if size == 126:
                size = struct.unpack(">H", self._read(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(size)
            opcode = first & 0x0F
            if opcode == 8:
                raise OSError("DevTools closed the page connection")
            if opcode in (9, 10):
                continue
            message += payload
            if not first & 0x80:
                continue
            reply, message = json.loads(message), b""
            if reply.get("id") == self.request_id:
                if "error" in reply:
                    raise OSError(f"DevTools {method} failed: {reply['error']}")
                return reply["result"]
