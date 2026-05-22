"""Enforce that every backend Django app is placed in exactly one CI shard.

A senior reviewer flagged on the missions PR that any new app needs to be placed
in one of the `backend-shard.matrix.shard[*].apps` entries in
`.github/workflows/ci.yml`, or its tests will not run in CI. This script is the
regression guard: it walks `src/` for `apps.py` files, parses the CI workflow's
shard config, and fails if any app is missing or appears in more than one shard.

Exit codes:
    0 — every app on disk is in exactly one shard.
    1 — one or more apps are missing from all shards, or duplicated across shards.

Output on failure is a `SHARD_COVERAGE:` block naming the offenders and (for
missing apps) suggesting a placement based on current shard sizes parsed from
the `# shard-N (~XXXX): ...` comments above each entry.
"""

from __future__ import annotations

from collections import defaultdict
import dataclasses
from pathlib import Path
import re
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

_APPS_FILENAME = "apps.py"
_MIGRATIONS_DIR = "migrations"
_TESTS_DIRS = frozenset({"tests"})
# Match a shard size comment like "# shard-1 (~1,461): world.magic ..." so the
# suggestion ordering uses authoritative numbers from ci.yml itself.
_SHARD_SIZE_COMMENT_RE = re.compile(r"#\s*shard-\d+\s*\(~([\d,]+)\)")


@dataclasses.dataclass(frozen=True)
class ShardEntry:
    """A single shard from `backend-shard.matrix.shard`."""

    name: str
    apps: tuple[str, ...]
    approx_size: int | None  # parsed from the `# shard-N (~XXXX)` comment


def _is_skipped_dir(path: Path) -> bool:
    """Return True when this path is inside a migrations or tests directory.

    Args:
        path: A filesystem path under SRC_DIR.

    Returns:
        True if any path component is a migrations or tests directory.
    """
    parts = set(path.parts)
    if _MIGRATIONS_DIR in parts:
        return True
    return bool(parts & _TESTS_DIRS)


def discover_apps_on_disk() -> set[str]:
    """Find every Django app under src/ by walking for apps.py files.

    Returns:
        A set of dotted app names, e.g. {"world.missions", "evennia_extensions"}.
    """
    apps: set[str] = set()
    for apps_py in SRC_DIR.rglob(_APPS_FILENAME):
        if _is_skipped_dir(apps_py):
            continue
        # Derive dotted name from path relative to SRC_DIR. The parent directory
        # of apps.py IS the app root, so its relative path becomes the dotted
        # name (e.g. src/world/missions/apps.py → world.missions).
        rel = apps_py.parent.relative_to(SRC_DIR)
        dotted = ".".join(rel.parts)
        apps.add(dotted)
    return apps


def parse_shards() -> list[ShardEntry]:
    """Parse the backend-shard matrix from .github/workflows/ci.yml.

    Returns:
        Ordered list of ShardEntry objects mirroring the YAML order.
    """
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    raw_shards = data["jobs"]["backend-shard"]["strategy"]["matrix"]["shard"]

    # Pre-extract the approx size comments by line scan; YAML drops comments.
    sizes = _approx_sizes_by_shard_name(text)

    shards: list[ShardEntry] = []
    for entry in raw_shards:
        name = entry["name"]
        apps_str = entry["apps"]
        apps = tuple(apps_str.split())
        shards.append(
            ShardEntry(name=name, apps=apps, approx_size=sizes.get(name)),
        )
    return shards


def _approx_sizes_by_shard_name(workflow_text: str) -> dict[str, int]:
    """Parse `# shard-N (~XXXX): ...` comments to get an approx size per shard.

    Args:
        workflow_text: The full text of the ci.yml workflow file.

    Returns:
        A mapping of shard name (`shard-N`) to the parsed approximate size.
        Shards without a matching comment are omitted; callers must tolerate that.
    """
    sizes: dict[str, int] = {}
    for line in workflow_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        match = _SHARD_SIZE_COMMENT_RE.search(stripped)
        if not match:
            continue
        # Pull the shard name from the same comment.
        name_match = re.search(r"shard-\d+", stripped)
        if name_match is None:
            continue
        size = int(match.group(1).replace(",", ""))
        sizes[name_match.group(0)] = size
    return sizes


def find_duplicates(shards: list[ShardEntry]) -> dict[str, list[str]]:
    """Return apps that appear in more than one shard.

    Args:
        shards: Parsed shard entries.

    Returns:
        A mapping of duplicated-app name to the list of shard names it
        appears in (only entries with >1 shard are included).
    """
    membership: dict[str, list[str]] = defaultdict(list)
    for shard in shards:
        for app in shard.apps:
            membership[app].append(shard.name)
    return {app: names for app, names in membership.items() if len(names) > 1}


def find_missing(disk_apps: set[str], shards: list[ShardEntry]) -> set[str]:
    """Return apps on disk that aren't placed in any shard.

    Args:
        disk_apps: The set of dotted app names found on disk.
        shards: Parsed shard entries.

    Returns:
        The set of apps present on disk but absent from every shard's apps list.
    """
    covered: set[str] = set()
    for shard in shards:
        covered.update(shard.apps)
    return disk_apps - covered


def _shard_sort_key(shard: ShardEntry) -> tuple[int, int]:
    """Sort key for shard suggestion order: smallest first.

    Args:
        shard: A parsed ShardEntry.

    Returns:
        (size, app-count) tuple. Size comes from the parsed comment when
        available; otherwise fall back to app-count alone (size=0 sorts first,
        but that just means malformed-comment shards appear before sized ones,
        which is acceptable — they're probably fresher and lighter).
    """
    return (shard.approx_size or 0, len(shard.apps))


def _format_missing_message(missing: Iterable[str], shards: list[ShardEntry]) -> str:
    """Build the user-facing message for missing apps.

    Args:
        missing: Apps that aren't in any shard.
        shards: Parsed shard entries (used to suggest placement).

    Returns:
        A multiline message ready to print.
    """
    lines = [
        "SHARD_COVERAGE: the following backend apps exist on disk but are not in any CI shard:",
    ]
    lines.extend(f"  - {app}" for app in sorted(missing))
    lines.append("")
    lines.append(
        "Add them to .github/workflows/ci.yml under backend-shard.matrix.shard[*].apps.",
    )
    lines.append("Suggested placement (current shard sizes, smallest first):")
    for shard in sorted(shards, key=_shard_sort_key):
        size_str = (
            f"~{shard.approx_size:,} tests"
            if shard.approx_size is not None
            else f"{len(shard.apps)} apps"
        )
        apps_str = " ".join(shard.apps)
        lines.append(f"  {shard.name} ({size_str}): {apps_str}")
    return "\n".join(lines)


def _format_duplicate_message(duplicates: dict[str, list[str]]) -> str:
    """Build the user-facing message for apps appearing in multiple shards.

    Args:
        duplicates: Mapping of app name to the shards it appears in.

    Returns:
        A multiline message ready to print.
    """
    lines = [
        "SHARD_COVERAGE: the following apps are listed in MORE than one shard:",
    ]
    lines.extend(f"  - {app}: {' and '.join(duplicates[app])}" for app in sorted(duplicates))
    lines.append("")
    lines.append(
        "Each app should appear in exactly one shard. Remove duplicate entries.",
    )
    return "\n".join(lines)


def main() -> int:
    """Run the shard coverage check.

    Returns:
        Process exit code: 0 when clean, 1 when violations are found.
    """
    disk_apps = discover_apps_on_disk()
    shards = parse_shards()

    duplicates = find_duplicates(shards)
    missing = find_missing(disk_apps, shards)

    if not duplicates and not missing:
        return 0

    if missing:
        print(_format_missing_message(missing, shards))
    if duplicates:
        if missing:
            print()
        print(_format_duplicate_message(duplicates))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
