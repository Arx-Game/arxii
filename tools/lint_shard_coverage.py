"""Enforce that every backend app's tests run in exactly one CI shard.

A senior reviewer flagged on the missions PR that any new app needs to be placed
in one of the `backend-shard.matrix.shard[*].apps` entries in
`.github/workflows/ci.yml`, or its tests will not run in CI. This script is the
regression guard. Two discovery modes feed the required set, because each has a
blind spot the other covers:

- **Django apps** — every `apps.py` under `src/` (skipping migrations/tests
  dirs). Catches new apps even before they grow tests.
- **Test-bearing packages** — any top-level package under `src/` (or
  `world.<name>`) containing a `test_*.py` with a real test (a `def test_` or a
  class subclassing *TestCase*). Catches packages like `core` and
  `integration_tests` that have tests but no `apps.py` — both were dark in CI
  before this mode existed (#2446).

Coverage semantics:

- A shard label must be a whole top-level package (`web`, `world.magic`).
  Dotted sub-app labels (`web.admin`, `integration_tests.pipeline`) are
  rejected — they look like coverage but run only that subpackage, which is
  how integration_tests' root-level modules went dark. Django test discovery
  recurses, so the whole-app label covers every nested package (web.admin
  rides on `web`).
- An app split below the app level uses `split_app`/`split_part`/`split_of`
  matrix fields (see tools/split_test_labels.py); the parts must cover
  1..split_of exactly once, and the app must not also appear as a label.
- Every required app must be covered exactly once across labels + splits.

Exit codes:
    0 — every required app is covered exactly once.
    1 — violations found; a `SHARD_COVERAGE:` block names the offenders and
        (for missing apps) suggests a placement based on the `# shard-N (~XXXs)`
        size comments above each entry.
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
# Match a shard size comment like "# shard-1 (~304s): world.magic ..." (older
# format was a test count, "# shard-1 (~2,544): ...") so the suggestion
# ordering uses authoritative numbers from ci.yml itself.
_SHARD_SIZE_COMMENT_RE = re.compile(r"#\s*shard-\d+\s*\(~([\d,]+)s?\)")
# A test_*.py file counts as real tests when it defines a test method or a
# TestCase subclass (the latter catches modules whose tests are all inherited
# from mixins). Config shims that merely match the filename pattern
# (server/conf/test_settings.py) match neither and are ignored.
_HAS_TESTS_RE = re.compile(r"^\s*def test_|^\s*class \w+\([^)]*TestCase", re.MULTILINE)


@dataclasses.dataclass(frozen=True)
class ShardEntry:
    """A single shard from `backend-shard.matrix.shard`."""

    name: str
    apps: tuple[str, ...]
    approx_size: int | None  # parsed from the `# shard-N (~XXXs)` comment
    split_app: str | None = None
    split_part: int | None = None
    split_of: int | None = None


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


def _has_real_tests(package_dir: Path) -> bool:
    """Return True when the package contains at least one real test module.

    Args:
        package_dir: A package directory under SRC_DIR.

    Returns:
        True if any non-__pycache__ test_*.py matches _HAS_TESTS_RE.
    """
    for path in package_dir.rglob("test_*.py"):
        if "__pycache__" in path.parts:
            continue
        if _HAS_TESTS_RE.search(path.read_text(encoding="utf-8")):
            return True
    return False


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


def discover_labelable_packages() -> dict[str, bool]:
    """Map every top-level package to whether it contains real tests.

    "Top-level" means an immediate package child of src/ or of src/world/
    (labelled `world.<name>`) — the only granularity shard labels may use.

    Returns:
        Mapping of dotted package name to has-real-tests.
    """
    packages: dict[str, bool] = {}
    for child in sorted(SRC_DIR.iterdir()):
        if not (child / "__init__.py").is_file():
            continue
        if child.name == "world":
            for sub in sorted(child.iterdir()):
                if (sub / "__init__.py").is_file():
                    packages[f"world.{sub.name}"] = _has_real_tests(sub)
        else:
            packages[child.name] = _has_real_tests(child)
    return packages


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
        apps = tuple(entry.get("apps", "").split())
        shards.append(
            ShardEntry(
                name=name,
                apps=apps,
                approx_size=sizes.get(name),
                split_app=entry.get("split_app"),
                split_part=entry.get("split_part"),
                split_of=entry.get("split_of"),
            ),
        )
    return shards


def _approx_sizes_by_shard_name(workflow_text: str) -> dict[str, int]:
    """Parse `# shard-N (~XXXs)` comments to get an approx size per shard.

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


def _ancestor_labels(app: str) -> list[str]:
    """Return the dotted ancestors of an app, outermost first.

    Args:
        app: A dotted app name, e.g. "web.admin".

    Returns:
        Ancestor labels, e.g. ["web"] — empty for top-level apps.
    """
    parts = app.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def check_labels(
    shards: list[ShardEntry],
    labelable: dict[str, bool],
) -> list[str]:
    """Validate that every shard label is a whole top-level package.

    Args:
        shards: Parsed shard entries.
        labelable: Output of discover_labelable_packages().

    Returns:
        Error strings for sub-app labels and labels matching nothing on disk.
    """
    errors: list[str] = []
    for shard in shards:
        for label in shard.apps:
            if label in labelable:
                continue
            if any(ancestor in labelable for ancestor in _ancestor_labels(label)):
                errors.append(
                    f"{shard.name}: '{label}' is a sub-app label — it silently skips "
                    f"sibling test modules. List the whole app (test discovery "
                    f"recurses), or use split_app for a managed split."
                )
            else:
                errors.append(f"{shard.name}: '{label}' does not match any package under src/.")
    return errors


def check_splits(shards: list[ShardEntry], labelable: dict[str, bool]) -> list[str]:
    """Validate split_app entries: parts must cover 1..split_of exactly once.

    Args:
        shards: Parsed shard entries.
        labelable: Output of discover_labelable_packages().

    Returns:
        Error strings for malformed or incomplete split configurations.
    """
    errors: list[str] = []
    parts_by_app: dict[str, list[tuple[int | None, int | None]]] = defaultdict(list)
    for shard in shards:
        if shard.split_app is not None:
            parts_by_app[shard.split_app].append((shard.split_part, shard.split_of))
    for app, parts in parts_by_app.items():
        if app not in labelable:
            errors.append(f"split_app '{app}' does not match any package under src/.")
        ofs = {of for _, of in parts}
        if len(ofs) != 1 or None in ofs:
            errors.append(f"split_app '{app}' has inconsistent split_of values: {sorted(ofs)}.")
            continue
        expected = list(range(1, next(iter(ofs)) + 1))
        got = sorted(part for part, _ in parts)
        if got != expected:
            errors.append(f"split_app '{app}' parts are {got}, expected exactly {expected}.")
    return errors


def coverage_by_app(
    required: Iterable[str],
    shards: list[ShardEntry],
) -> dict[str, list[str]]:
    """Map each required app to the shard names that run its tests.

    An app is covered by a shard when the shard lists the app itself or a
    dotted ancestor (test discovery recurses into subpackages), or when the
    shard carries one part of a split of that app (counted once across all
    parts, since together the parts run the app exactly once).

    Args:
        required: Apps that must be covered.
        shards: Parsed shard entries.

    Returns:
        Mapping of app name to covering shard names (possibly empty).
    """
    label_shards: dict[str, list[str]] = defaultdict(list)
    split_apps: set[str] = set()
    for shard in shards:
        for label in shard.apps:
            label_shards[label].append(shard.name)
        if shard.split_app is not None:
            split_apps.add(shard.split_app)

    coverage: dict[str, list[str]] = {}
    for app in required:
        covering: list[str] = []
        for label in (app, *_ancestor_labels(app)):
            covering.extend(label_shards.get(label, []))
        if app in split_apps:
            covering.append(f"split:{app}")
        coverage[app] = covering
    return coverage


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
        missing: Apps that aren't covered by any shard.
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
            f"~{shard.approx_size}s" if shard.approx_size is not None else f"{len(shard.apps)} apps"
        )
        apps_str = " ".join(shard.apps)
        lines.append(f"  {shard.name} ({size_str}): {apps_str}")
    return "\n".join(lines)


def _format_duplicate_message(duplicates: dict[str, list[str]]) -> str:
    """Build the user-facing message for apps covered more than once.

    Args:
        duplicates: Mapping of app name to the shard names covering it.

    Returns:
        A multiline message ready to print.
    """
    lines = [
        "SHARD_COVERAGE: the following apps are covered MORE than once (tests run redundantly):",
    ]
    lines.extend(f"  - {app}: {' and '.join(duplicates[app])}" for app in sorted(duplicates))
    lines.append("")
    lines.append(
        "Each app should be covered exactly once. Remove duplicate or overlapping entries.",
    )
    return "\n".join(lines)


def main() -> int:
    """Run the shard coverage check.

    Returns:
        Process exit code: 0 when clean, 1 when violations are found.
    """
    labelable = discover_labelable_packages()
    # Required = every Django app, plus every top-level package with real
    # tests (core, integration_tests have no apps.py but their tests matter).
    required = discover_apps_on_disk() | {
        package for package, has_tests in labelable.items() if has_tests
    }
    shards = parse_shards()

    errors = check_labels(shards, labelable) + check_splits(shards, labelable)

    coverage = coverage_by_app(required, shards)
    missing = {app for app, covering in coverage.items() if not covering}
    duplicates = {app: covering for app, covering in coverage.items() if len(covering) > 1}

    if not errors and not missing and not duplicates:
        return 0

    if errors:
        print("SHARD_COVERAGE: invalid shard configuration:")
        for error in errors:
            print(f"  - {error}")
    if missing:
        if errors:
            print()
        print(_format_missing_message(missing, shards))
    if duplicates:
        if errors or missing:
            print()
        print(_format_duplicate_message(duplicates))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
