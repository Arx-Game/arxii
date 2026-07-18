"""Content-load health helpers (#2501): group, allowlist, and report skips.

``load_world_content`` (``core_management.content_fixtures``) records each
skipped row as a string in ``WorldLoadResult.skipped``. Most read
``"{source_path}: {Model} could not be loaded: ..."``, but not all: a stale
model reads ``"{source_path}: stale model {model!r} (renamed or removed) —
skipped."``, and a model missing ``NaturalKeyMixin`` reads
``"{location}: model {Model} lacks NaturalKeyMixin — ..."`` where ``location``
falls back to ``model._meta.label`` (not a source path) when the failure
isn't tied to one file. Those skips scroll past silently today. This module
is the pure-python layer a later task wires into the CLI: group skips by
source file, load a ``KNOWN_DRIFT.txt`` allowlist of substring patterns for
expected/pre-existing drift, partition skips into known vs. unexpected, and
render a human-readable health report.

Import-safe without Django configured (same convention as
``content_fixtures.py``): no Django imports at module scope, so tooling and
tests can import this module standalone.
"""

from __future__ import annotations

from pathlib import Path

KNOWN_DRIFT_FILENAME = "KNOWN_DRIFT.txt"
UNKNOWN_SOURCE = "<unknown>"


def group_skips(skipped: list[str]) -> dict[str, list[str]]:
    """Group skip messages by their source-path prefix (text before ``": "``).

    A skip message missing the ``": "`` separator groups under
    ``"<unknown>"``. Insertion order is preserved for both the group keys and
    the messages within each group.
    """
    grouped: dict[str, list[str]] = {}
    for message in skipped:
        source, sep, _rest = message.partition(": ")
        key = source if sep else UNKNOWN_SOURCE
        grouped.setdefault(key, []).append(message)
    return grouped


def load_known_drift(content_root: Path) -> list[str]:
    """Read ``<content_root>/fixtures/KNOWN_DRIFT.txt`` into a pattern list.

    One substring pattern per line; blank lines and ``#``-comment lines are
    stripped. Returns ``[]`` when the file is absent.
    """
    drift_path = content_root / "fixtures" / KNOWN_DRIFT_FILENAME
    if not drift_path.is_file():
        return []

    patterns: list[str] = []
    for raw_line in drift_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def partition_skips(skipped: list[str], patterns: list[str]) -> tuple[list[str], list[str]]:
    """Split ``skipped`` into ``(known, unexpected)`` by substring match.

    A skip is "known" when any pattern in ``patterns`` is a substring of it.
    Order is preserved within each list.
    """
    known: list[str] = []
    unexpected: list[str] = []
    for message in skipped:
        if any(pattern in message for pattern in patterns):
            known.append(message)
        else:
            unexpected.append(message)
    return known, unexpected


def render_health_report(skipped: list[str], patterns: list[str]) -> tuple[list[str], bool]:
    """Render human-readable report lines for ``skipped`` plus a health verdict.

    Lines cover per-source skip counts, the total known-drift count, and each
    unexpected skip verbatim. ``healthy`` is ``True`` iff there are no
    unexpected skips (an empty ``skipped`` list is healthy).
    """
    grouped = group_skips(skipped)
    known, unexpected = partition_skips(skipped, patterns)

    lines: list[str] = []
    for source, messages in grouped.items():
        lines.append(f"{source}: {len(messages)} skipped")
    lines.append(f"known drift: {len(known)}")

    if unexpected:
        lines.append(f"unexpected: {len(unexpected)}")
        lines.extend(unexpected)

    return lines, not unexpected
