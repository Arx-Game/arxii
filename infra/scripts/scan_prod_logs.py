#!/usr/bin/env python3
"""Read-only production traceback scanner.

The default source is the production host's rotated ``server.log`` files. The
SSH command set is intentionally fixed to ``find`` and ``tail``; this tool
never accepts or executes a remote shell command supplied by the caller.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

LOG_DIR = "/var/log/arxii"
TRACEBACK_HEADER = "Traceback (most recent call last):"
MAX_TRACEBACK_LINES = 200
MAX_DAYS = 30
MAX_FILES = 8
MAX_TAIL_BYTES = 4_000_000
MAX_TOTAL_BYTES = 16_000_000
MAX_MATCHES = 100
LOG_NAME_RE = re.compile(r"server\.log(?:\.\d{4}_\d{2}_\d{2}(?:__\d+)?)?")
ROTATION_RE = re.compile(r"server\.log\.(?P<date>\d{4}_\d{2}_\d{2})(?:__(?P<part>\d+))?")
SSH_TARGET = "arxii-prod"
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(?P<key>password|passwd|secret|token|authorization|cookie|sentry_dsn)"
    r"(?P<separator>\s*[=:]\s*)(?P<value>[^\s,;]+)"
)


class ScanError(RuntimeError):
    """Raised when a source cannot be read without changing it."""


@dataclass(frozen=True)
class TracebackMatch:
    """A bounded traceback extracted from one log source."""

    source: str
    start_line: int
    text: str


@dataclass(frozen=True)
class ScanResult:
    """Bounded scan output and its completeness warning."""

    matches: list[TracebackMatch]
    scanned_sources: list[str]
    limits_reached: bool


def redact(line: str) -> str:
    """Redact common credential-shaped values before printing log content."""
    safe_line = CONTROL_RE.sub(lambda match: f"\\x{ord(match.group(0)):02x}", line)
    return SENSITIVE_VALUE_RE.sub(
        lambda match: f"{match.group('key')}{match.group('separator')}<redacted>",
        safe_line,
    )


def _is_traceback_boundary(line: str, seen_frame: bool) -> bool:
    """Return whether an unindented line terminates a traceback."""
    stripped = line.strip()
    if not stripped or not seen_frame or line[:1].isspace():
        return False
    return not stripped.startswith(("During handling of the above", "The above exception"))


def extract_tracebacks(
    lines: Iterable[str], *, source: str, max_matches: int
) -> list[TracebackMatch]:
    """Extract at most ``max_matches`` bounded traceback blocks from lines.

    The production logger writes the traceback header and Python frames as
    separate lines. A traceback ends at its first unindented exception line,
    or at the hard line limit when a malformed burst has no terminator.
    """
    matches: list[TracebackMatch] = []
    active: list[str] = []
    start_line = 0
    seen_frame = False

    def finish() -> None:
        nonlocal active, seen_frame
        if active and len(matches) < max_matches:
            matches.append(
                TracebackMatch(
                    source=source,
                    start_line=start_line,
                    text="\n".join(redact(item.rstrip("\n")) for item in active),
                )
            )
        active = []
        seen_frame = False

    for line_number, line in enumerate(lines, start=1):
        if TRACEBACK_HEADER in line:
            finish()
            if len(matches) >= max_matches:
                break
            active = [line]
            start_line = line_number
            continue
        if not active:
            continue

        active.append(line)
        # Twisted's classic log formatter prefixes continuation lines with a
        # tab. Normalize only for structure detection; retain the source text.
        continuation = line.removeprefix("\t")
        if continuation.lstrip().startswith('File "'):
            seen_frame = True
        if _is_traceback_boundary(continuation, seen_frame) or len(active) >= MAX_TRACEBACK_LINES:
            finish()

    if active and len(matches) < max_matches:
        finish()
    return matches


def _validate_target(target: str) -> str:
    if target != SSH_TARGET:
        raise ScanError(f"SSH target must be {SSH_TARGET!r}")
    return target


def _run_ssh(target: str, args: Sequence[str]) -> bytes:
    """Run one fixed, non-interactive SSH read command."""
    try:
        completed = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "RequestTTY=no",
                "--",
                _validate_target(target),
                *args,
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise ScanError("ssh is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise ScanError("read-only SSH command timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise ScanError(f"read-only SSH command failed: {detail or 'unknown error'}") from exc
    return completed.stdout


def discover_remote_logs(*, target: str, days: int, max_files: int) -> list[str]:
    """Find recent server logs without running a caller-provided command."""
    output = _run_ssh(
        target,
        [
            "find",
            LOG_DIR,
            "-maxdepth",
            "1",
            "-type",
            "f",
            "-name",
            "'[s]erver.log*'",
            "-readable",
            "-mtime",
            f"-{days}",
            "-print",
        ],
    )
    paths: list[str] = []
    for raw_path in output.decode("utf-8", errors="replace").splitlines():
        path = PurePosixPath(raw_path)
        if path.parent != PurePosixPath(LOG_DIR) or not LOG_NAME_RE.fullmatch(path.name):
            continue
        paths.append(path.name)
    # Scan the live file first, then the newest dated rotations.
    current = [name for name in paths if name == "server.log"]
    rotated = sorted(
        (name for name in paths if name != "server.log"),
        key=lambda name: (
            ROTATION_RE.fullmatch(name).group("date"),
            int(ROTATION_RE.fullmatch(name).group("part") or 0),
        ),
        reverse=True,
    )
    return (current + rotated)[:max_files]


def read_remote_log(*, target: str, name: str, max_bytes: int) -> bytes:
    """Read a bounded tail of one validated production log file."""
    if not LOG_NAME_RE.fullmatch(name):
        raise ScanError(f"unexpected remote log name: {name}")
    return _run_ssh(target, ["tail", "-c", str(max_bytes), "--", f"{LOG_DIR}/{name}"])


def read_local_log(path: Path, max_bytes: int) -> bytes:
    """Read a bounded tail of a local fixture or copied production log."""
    try:
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - max_bytes))
            return handle.read(max_bytes)
    except OSError as exc:
        raise ScanError(f"cannot read {path}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ssh-target",
        default="arxii-prod",
        help="SSH host alias (default: arxii-prod); use --file for offline scanning",
    )
    parser.add_argument("--file", action="append", type=Path, help="local log file; repeatable")
    parser.add_argument(
        "--days", type=int, default=2, help="remote mtime window, up to 30 days (default: 2)"
    )
    parser.add_argument(
        "--max-files", type=int, default=4, help="remote files, up to 8 (default: 4)"
    )
    parser.add_argument(
        "--tail-bytes",
        type=int,
        default=1_000_000,
        help="bytes read per file, up to 4M (default: 1M)",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=4_000_000,
        help="total bytes read, up to 16M (default: 4M)",
    )
    parser.add_argument(
        "--max-matches", type=int, default=20, help="tracebacks printed, up to 100 (default: 20)"
    )
    parser.add_argument("--json", action="store_true", help="emit bounded machine-readable JSON")
    return parser


def _validate_options(options: argparse.Namespace) -> None:
    if options.file and options.days != 2:
        raise ScanError("--days applies only to remote logs and cannot be combined with --file")
    limits = {
        "days": MAX_DAYS,
        "max_files": MAX_FILES,
        "tail_bytes": MAX_TAIL_BYTES,
        "max_bytes": MAX_TOTAL_BYTES,
        "max_matches": MAX_MATCHES,
    }
    for name, maximum in limits.items():
        value = getattr(options, name)
        if value < 1:
            raise ScanError(f"--{name.replace('_', '-')} must be positive")
        if value > maximum:
            raise ScanError(f"--{name.replace('_', '-')} cannot exceed {maximum}")
    if options.tail_bytes > options.max_bytes:
        raise ScanError("--tail-bytes cannot exceed --max-bytes")
    if not options.file:
        _validate_target(options.ssh_target)


def scan(options: argparse.Namespace) -> ScanResult:
    """Read selected sources and return tracebacks plus source labels."""
    _validate_options(options)
    if options.file:
        sources = [
            (
                str(path),
                lambda path=path, limit=options.tail_bytes: read_local_log(path, limit),
            )
            for path in options.file
        ]
    else:
        names = discover_remote_logs(
            target=options.ssh_target, days=options.days, max_files=options.max_files
        )
        sources = [
            (
                name,
                lambda name=name, limit=options.tail_bytes: read_remote_log(
                    target=options.ssh_target, name=name, max_bytes=limit
                ),
            )
            for name in names
        ]

    matches: list[TracebackMatch] = []
    scanned: list[str] = []
    remaining_bytes = options.max_bytes
    for source, reader in sources:
        if remaining_bytes <= 0 or len(matches) >= options.max_matches:
            break
        payload = reader()
        payload = payload[:remaining_bytes]
        remaining_bytes -= len(payload)
        scanned.append(source)
        matches.extend(
            extract_tracebacks(
                payload.decode("utf-8", errors="replace").splitlines(),
                source=source,
                max_matches=options.max_matches - len(matches),
            )
        )
    return ScanResult(
        matches=matches,
        scanned_sources=scanned,
        limits_reached=remaining_bytes <= 0 or len(matches) >= options.max_matches,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scanner and return a shell status."""
    parser = _parser()
    options = parser.parse_args(argv)
    try:
        result = scan(options)
    except ScanError as exc:
        print(f"scan-prod-logs: {exc}", file=sys.stderr)
        return 2

    if options.json:
        print(
            json.dumps(
                {
                    "bounded": True,
                    "limits_reached": result.limits_reached,
                    "may_be_incomplete": True,
                    "scanned_sources": result.scanned_sources,
                    "tracebacks": [asdict(item) for item in result.matches],
                }
            )
        )
        return 0
    print(
        f"Scanned {len(result.scanned_sources)} source(s); found "
        f"{len(result.matches)} traceback(s)."
    )
    print(
        "Bounded scan: results may be incomplete (the tail can start mid-traceback); "
        f"limits reached: {result.limits_reached}."
    )
    for index, match in enumerate(result.matches, start=1):
        print(f"\n=== traceback {index}: {match.source} (tail line {match.start_line}) ===")
        print(match.text)
    if not result.matches:
        print("No traceback headers found in the bounded scan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
