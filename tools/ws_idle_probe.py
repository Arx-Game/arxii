"""Measure how long a game websocket survives with no traffic on it.

Written for #3745, where every silent session re-logged in every 127 seconds.
It needs no credentials and no server access: it opens a plain websocket to the
public address, logs every frame with a timestamp, and reports when and how the
connection ends. Run it with a ping interval to prove the timeout is an idle
timer rather than a cap on connection age.

    uv run python tools/ws_idle_probe.py play.arx2.com            # idle
    uv run python tools/ws_idle_probe.py play.arx2.com --ping 30  # kept warm

Two samples on 2026-09-12 ended at 125.613s and 125.595s with a bare TCP FIN
and no close frame; a third, pinging every 30s, was still open when its 420s
window ran out. Those numbers are what ADR-0291 pins the keepalive interval to,
so re-run this before arguing that the interval should change.
"""

import argparse
import base64
import os
import socket
import ssl
import struct
import sys
import time

CONTINUATION_LENGTHS = {126: (4, ">H"), 127: (10, ">Q")}
MIN_CLOSE_PAYLOAD = 2  # a close frame carries a 2-byte code before any reason text
FRAME_HEADER = 2  # opcode byte + length byte, before any extended length
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA


def build_handshake(host: str, path: str) -> bytes:
    """The client half of RFC 6455's opening handshake."""
    key = base64.b64encode(os.urandom(16)).decode()
    return (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode()


def masked_frame(opcode: int, payload: bytes = b"") -> bytes:
    """A client frame. Client-to-server frames must be masked."""
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
    return bytes([0x80 | opcode, 0x80 | len(payload)]) + mask + masked


def split_frame(buffer: bytes) -> tuple[int, bytes, bytes] | None:
    """Peel one complete frame off the head of ``buffer``, or None if it is short."""
    if len(buffer) < FRAME_HEADER:
        return None
    opcode = buffer[0] & 0x0F
    length = buffer[1] & 0x7F
    offset = FRAME_HEADER
    if length in CONTINUATION_LENGTHS:
        offset, fmt = CONTINUATION_LENGTHS[length]
        if len(buffer) < offset:
            return None
        length = struct.unpack(fmt, buffer[FRAME_HEADER:offset])[0]
    if len(buffer) < offset + length:
        return None
    return opcode, buffer[offset : offset + length], buffer[offset + length :]


class Probe:
    """One connection, from handshake to whatever ends it."""

    def __init__(self, host: str, path: str, seconds: float, ping_every: float) -> None:
        self.host = host
        self.path = path
        self.seconds = seconds
        self.ping_every = ping_every
        self.started = time.monotonic()
        self.socket = self.connect()

    def log(self, message: str) -> None:
        print(f"[{time.monotonic() - self.started:9.3f}s] {message}", flush=True)

    def connect(self) -> ssl.SSLSocket:
        context = ssl.create_default_context()
        raw = socket.create_connection((self.host, 443), timeout=15)
        connected = context.wrap_socket(raw, server_hostname=self.host)
        self.log(f"connected to {connected.getpeername()}")
        connected.sendall(build_handshake(self.host, self.path))
        connected.settimeout(1.0)
        return connected

    def read_handshake_response(self) -> bytes:
        """Return whatever framed bytes arrived behind the response headers."""
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            buffer += self.socket.recv(4096)
        head, _, rest = buffer.partition(b"\r\n\r\n")
        status = head.decode(errors="replace").splitlines()[0]
        self.log(f"handshake: {status}")
        if " 101 " not in status:
            refusal = f"no upgrade - server said: {status}"
            raise SystemExit(refusal)
        return rest

    def handle_frame(self, opcode: int, payload: bytes) -> bool:
        """Log one frame. Returns False when it ends the connection."""
        if opcode == OPCODE_CLOSE:
            has_code = len(payload) >= MIN_CLOSE_PAYLOAD
            code = struct.unpack(">H", payload[:MIN_CLOSE_PAYLOAD])[0] if has_code else None
            self.log(f"<- CLOSE code={code} reason={payload[MIN_CLOSE_PAYLOAD:]!r}")
            return False
        if opcode == OPCODE_PING:
            self.log(f"<- PING {payload!r}")
            self.socket.sendall(masked_frame(OPCODE_PONG, payload))
        elif opcode == OPCODE_PONG:
            self.log(f"<- PONG {payload!r}")
        else:
            self.log(f"<- opcode={opcode} len={len(payload)} {payload[:120]!r}")
        return True

    def run(self) -> None:
        buffer = self.read_handshake_response()
        last_ping = time.monotonic()
        while time.monotonic() - self.started < self.seconds:
            if self.ping_every and time.monotonic() - last_ping >= self.ping_every:
                self.socket.sendall(masked_frame(OPCODE_PING, b"probe"))
                self.log("-> PING")
                last_ping = time.monotonic()
            try:
                chunk = self.socket.recv(4096)
            except TimeoutError:
                continue
            except OSError as exc:
                self.log(f"socket error: {exc!r}")
                return
            if not chunk:
                self.log("closed by peer: bare TCP FIN, no close frame")
                return
            buffer += chunk
            while True:
                frame = split_frame(buffer)
                if frame is None:
                    break
                opcode, payload, buffer = frame
                if not self.handle_frame(opcode, payload):
                    return
        self.log("window ended, connection still open")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("host", help="public hostname, e.g. play.arx2.com")
    parser.add_argument("--path", default="/ws/game/")
    parser.add_argument("--seconds", type=float, default=420.0, help="how long to watch")
    parser.add_argument("--ping", type=float, default=0.0, help="ping every N seconds (0 = idle)")
    args = parser.parse_args(argv)
    Probe(args.host, args.path, args.seconds, args.ping).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
