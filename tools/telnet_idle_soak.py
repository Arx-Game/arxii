"""Run a bounded, authenticated idle soak against one Telnet listener.

The probe intentionally records protocol metadata only. It never prints the
username, password, command input, or server text. Use it against a disposable
or explicitly approved account and keep the JSON report outside the checkout.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time

MAX_SECONDS = 3600.0
DEFAULT_SECONDS = 600.0
IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250
SE = 240
NOP = 241
AYT = 246


@dataclass
class TelnetEvents:
    """Counters for Telnet control traffic, without retaining payloads."""

    control_frames: int = 0
    keepalive_frames: int = 0
    application_bytes: int = 0
    _in_subnegotiation: bool = field(default=False, init=False, repr=False)
    _pending: bytes = field(default=b"", init=False, repr=False)

    def consume(  # noqa: C901, PLR0912 - one branch per Telnet framing state
        self, data: bytes
    ) -> list[bytes]:
        """Count server traffic and return required negotiation replies.

        A recv boundary may split any Telnet command. Keep only incomplete
        protocol bytes, never payload text, and prepend them to the next read.
        """
        replies: list[bytes] = []
        data = self._pending + data
        self._pending = b""
        index = 0
        while index < len(data):
            byte = data[index]
            if self._in_subnegotiation:
                if byte != IAC:
                    index += 1
                    continue
                if index + 1 >= len(data):
                    self._pending = data[index:]
                    break
                if data[index + 1] == SE:
                    self._in_subnegotiation = False
                    self.control_frames += 1
                index += 2
                continue
            if byte != IAC:
                self.application_bytes += 1
                index += 1
                continue
            if index + 1 >= len(data):
                self._pending = data[index:]
                break
            command = data[index + 1]
            if command == IAC:
                self.application_bytes += 1
                index += 2
                continue
            if command == SB:
                self._in_subnegotiation = True
                self.control_frames += 1
                index += 2
                continue
            if command in {DO, DONT, WILL, WONT} and index + 2 >= len(data):
                self._pending = data[index:]
                break
            self.control_frames += 1
            if command in {NOP, AYT}:
                self.keepalive_frames += 1
            if command in {DO, DONT, WILL, WONT}:
                option = data[index + 2]
                response = {DO: WONT, DONT: WONT, WILL: DONT, WONT: DONT}[command]
                replies.append(bytes((IAC, response, option)))
                index += 3
            else:
                index += 2
        return replies

    def reset_counters(self) -> None:
        """Start post-auth accounting without discarding parser state."""
        self.control_frames = 0
        self.keepalive_frames = 0
        self.application_bytes = 0


def bounded_seconds(value: str) -> float:
    """Parse a positive soak duration with a hard upper bound."""
    seconds = float(value)
    if not 0 < seconds <= MAX_SECONDS:
        raise argparse.ArgumentTypeError(f"seconds must be > 0 and <= {MAX_SECONDS:g}")
    return seconds


def revision() -> str:
    """Return the local revision when available, never failing the probe."""
    configured = os.environ.get("LIVENESS_DEPLOYMENT_REVISION", "").strip()
    if configured:
        return configured
    try:
        return subprocess.run(
            [shutil.which("git") or "git", "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def config_id(config: dict[str, object]) -> str:
    """Hash non-secret probe configuration for report correlation."""
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.blake2b(encoded, digest_size=8).hexdigest()


def strip_ansi(data: bytes) -> str:
    """Normalize prompt text only for matching; never include it in reports."""
    return re.sub(rb"\x1b\[[0-9;]*[A-Za-z]", b"", data).decode(errors="ignore")


class IdleSoak:
    """One authenticated plain or TLS Telnet connection."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.started_monotonic = time.monotonic()
        self.started_at = datetime.now(UTC)
        self.events = TelnetEvents()
        self.socket: socket.socket | ssl.SSLSocket | None = None
        self.buffer = b""

    def connect(self) -> socket.socket | ssl.SSLSocket:
        """Open the configured listener with a bounded connect timeout."""
        raw = socket.create_connection((self.args.host, self.args.port), timeout=15)
        if not self.args.tls:
            raw.settimeout(1.0)
            return raw
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        if self.args.insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        wrapped = context.wrap_socket(raw, server_hostname=self.args.host)
        wrapped.settimeout(1.0)
        return wrapped

    def receive_until(self, pattern: re.Pattern[str], deadline: float) -> None:
        """Read until a configured prompt or raise a bounded error."""
        while time.monotonic() < deadline:
            try:
                chunk = self.socket.recv(4096)  # type: ignore[union-attr]
            except TimeoutError:
                continue
            if not chunk:
                raise ConnectionError("peer closed before expected login prompt")
            self.buffer += chunk
            replies = self.events.consume(chunk)
            for reply in replies:
                self.socket.sendall(reply)  # type: ignore[union-attr]
            if pattern.search(strip_ansi(self.buffer)):
                return
        raise TimeoutError(f"prompt {pattern.pattern!r} not received before deadline")

    def send_line(self, value: str) -> None:
        """Send one credential line without logging its value."""
        self.socket.sendall(value.encode() + b"\r\n")  # type: ignore[union-attr]

    def authenticate(self) -> None:
        """Complete the configured username/password prompt exchange."""
        username = os.environ.get(self.args.username_env, "")
        password = os.environ.get(self.args.password_env, "")
        if not username or not password:
            raise ValueError(
                f"set {self.args.username_env} and {self.args.password_env}; values are never reported"
            )
        deadline = time.monotonic() + self.args.login_timeout
        self.receive_until(re.compile(self.args.username_prompt, re.IGNORECASE), deadline)
        self.send_line(username)
        self.buffer = b""
        self.receive_until(re.compile(self.args.password_prompt, re.IGNORECASE), deadline)
        self.send_line(password)
        self.buffer = b""
        self.receive_until(re.compile(self.args.ready_pattern, re.IGNORECASE), deadline)
        self.events.reset_counters()

    def run(self) -> dict[str, object]:
        """Run authentication and then observe the idle interval."""
        config: dict[str, object] = {
            "host": self.args.host,
            "port": self.args.port,
            "tls": self.args.tls,
            "tls_verify": self.args.tls and not self.args.insecure,
            "seconds": self.args.seconds,
            "login_timeout": self.args.login_timeout,
            "username_prompt": self.args.username_prompt,
            "password_prompt": self.args.password_prompt,
            "ready_pattern": self.args.ready_pattern,
        }
        result: dict[str, object] = {
            "schema": "arxii.liveness.telnet.v1",
            "revision": revision(),
            "configuration": config,
            "config_id": config_id(config),
            "started_at": self.started_at.isoformat(),
            "status": "error",
            "manual_reconnect_required": None,
        }
        try:
            self.socket = self.connect()
            self.authenticate()
            idle_started = time.monotonic()
            deadline = idle_started + self.args.seconds
            while time.monotonic() < deadline:
                try:
                    chunk = self.socket.recv(4096)
                except TimeoutError:
                    continue
                if not chunk:
                    result["status"] = "failed"
                    result["manual_reconnect_required"] = True
                    result["failure"] = "peer_closed_before_bound"
                    break
                replies = self.events.consume(chunk)
                for reply in replies:
                    self.socket.sendall(reply)
            else:
                result["status"] = "passed"
                result["manual_reconnect_required"] = False
            result["elapsed_seconds"] = round(time.monotonic() - idle_started, 3)
            result["control_frames"] = self.events.control_frames
            result["keepalive_frames"] = self.events.keepalive_frames
            result["application_bytes_after_login"] = self.events.application_bytes
        except (ConnectionError, OSError, TimeoutError, ValueError, ssl.SSLError) as exc:
            result["failure"] = type(exc).__name__
            result["failure_detail"] = str(exc)[:160]
        finally:
            if self.socket is not None:
                self.socket.close()
            result["ended_at"] = datetime.now(UTC).isoformat()
        return result


def build_parser() -> argparse.ArgumentParser:
    """Build the public command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("host")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--tls", action="store_true")
    parser.add_argument(
        "--insecure", action="store_true", help="disable TLS verification (rehearsal only)"
    )
    parser.add_argument("--seconds", type=bounded_seconds, default=DEFAULT_SECONDS)
    parser.add_argument("--login-timeout", type=bounded_seconds, default=30.0)
    parser.add_argument("--username-env", default="ARXII_SOAK_TELNET_USERNAME")
    parser.add_argument("--password-env", default="ARXII_SOAK_TELNET_PASSWORD")
    parser.add_argument("--username-prompt", default=r"(?:user(?:name)?|login)\s*[:>]")
    parser.add_argument("--password-prompt", default=r"password\s*[:>]")
    parser.add_argument("--ready-pattern", default=r"(?:^|[\r\n])\s*[>\]]\s*$")
    parser.add_argument("--report", type=argparse.FileType("w"), metavar="PATH")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the probe and emit a secret-free JSON result."""
    args = build_parser().parse_args(argv)
    if not args.host or any(char.isspace() for char in args.host) or "@" in args.host:
        raise SystemExit("host must not contain whitespace or userinfo")
    if not 1 <= args.port <= 65535:
        raise SystemExit("port must be between 1 and 65535")
    if args.insecure and not args.tls:
        raise SystemExit("--insecure requires --tls")
    result = IdleSoak(args).run()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report:
        os.fchmod(args.report.fileno(), 0o600)
        args.report.write(rendered)
        args.report.close()
    print(rendered, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
