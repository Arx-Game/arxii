#!/usr/bin/env python3
"""Build Django fixtures from the private content repository (#944).

NOT a management command (repo rule) — a tools script wrapping
core_management.content_fixtures. The content checkout is located via the
``CONTENT_REPO_PATH`` environment variable (set it in ``src/.env``); the
repository is deliberately never named in this codebase.

Usage:
    uv run python tools/build_content_fixtures.py            # build fixtures
    uv run python tools/build_content_fixtures.py --check    # validate only
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from core_management.content_fixtures import (  # noqa: E402
    BuildResult,
    ContentError,
    WorldLoadResult,
    build_all,
    write_fixtures,
)
from core_management.content_repo import load_dotenv_content_path  # noqa: E402


class _ExitEarly(Exception):
    """Internal control-flow signal carrying an exit code.

    Lets each validation/setup step below print its own clean stderr message
    and bail out via a single ``raise``, instead of every caller up the chain
    needing its own ``if error: return code`` branch — that branching is what
    pushed ``main()`` over ruff's return-count/complexity limits (#2266
    review fix) once environmental-error handling was added alongside the
    original content-shape errors.
    """

    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__(code)


def _require_content_root(args: argparse.Namespace) -> Path:
    """Resolve + validate the content checkout path, or raise ``_ExitEarly(2)``."""
    content_path = args.content_path or load_dotenv_content_path()
    if not content_path:
        print(
            "CONTENT_REPO_PATH is not set. Add it to src/.env pointing at your "
            "local checkout of the private content repository.",
            file=sys.stderr,
        )
        raise _ExitEarly(2)
    content_root = Path(content_path).expanduser()
    if not content_root.is_dir():
        print(f"Content path does not exist: {content_root}", file=sys.stderr)
        raise _ExitEarly(2)
    return content_root


def _configure_django() -> None:
    """Import + configure Django, or raise ``_ExitEarly(2)`` with a clean hint.

    Needed even for --check (#2266): npc_roles/'s optional faction_affiliation
    field is validated by an eager DB lookup, same as every other domain's
    shape validation. Settings resolve .env relative to src/. Harmless for
    domains that don't touch the DB.
    """
    import django  # noqa: PLC0415
    from django.core.exceptions import ImproperlyConfigured  # noqa: PLC0415

    os.chdir(SRC_ROOT)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    try:
        django.setup()
    except ImproperlyConfigured as exc:
        print(
            f"Django is not configured: {exc}\n"
            "Hint: a content-only author still needs src/.env with SECRET_KEY/"
            "DATABASE_URL set — the npc_roles/ domain's faction_affiliation "
            "field validates by querying the dev DB, so Django must be able "
            "to start even for --check.",
            file=sys.stderr,
        )
        raise _ExitEarly(2) from exc


def _build_content(content_root: Path) -> BuildResult:
    """Run ``build_all``, or raise ``_ExitEarly`` with a clean stderr message."""
    from django.db import Error as DjangoDbError  # noqa: PLC0415

    try:
        return build_all(content_root)
    except ContentError as exc:
        print(str(exc), file=sys.stderr)
        raise _ExitEarly(1) from exc
    except DjangoDbError as exc:
        print(
            f"Database error while validating content: {exc}\n"
            "Hint: run `arx manage migrate` to bring the dev DB schema up to date.",
            file=sys.stderr,
        )
        raise _ExitEarly(2) from exc


def _load_world(content_root: Path) -> WorldLoadResult:
    """Run ``load_world_content``, or raise ``_ExitEarly`` with a clean stderr message.

    Sequences content fixtures -> grid bundles -> deferred natural-key retry
    (#2448) — replaces the old bare ``build_all`` + ``load_entries`` pair so a
    ``StartingArea`` fixture's ``default_starting_room`` (a room natural key
    the grid bundles, not the content fixtures, create) resolves in one run.
    """
    from django.db import Error as DjangoDbError  # noqa: PLC0415

    from core_management.content_fixtures import load_world_content  # noqa: PLC0415

    try:
        return load_world_content(content_root)
    except ContentError as exc:
        print(str(exc), file=sys.stderr)
        raise _ExitEarly(1) from exc
    except DjangoDbError as exc:
        print(
            f"Database error while loading content: {exc}\n"
            "Hint: run `arx manage migrate` to bring the dev DB schema up to date.",
            file=sys.stderr,
        )
        raise _ExitEarly(2) from exc


def _print_load_report(world_result: WorldLoadResult) -> None:
    """Print the ``--load`` summary: content counts, grid counts, deferred, skips."""
    print(f"loaded: {world_result.created} created, {world_result.updated} updated.")
    if world_result.deferred_resolved:
        print(
            f"deferred-resolved: {world_result.deferred_resolved} object(s) "
            "(unblocked once the grid bundles loaded)."
        )
    grid = world_result.grid
    grid_created = grid.created_areas + grid.created_rooms + grid.created_exits
    grid_updated = grid.updated_areas + grid.updated_rooms + grid.updated_exits
    if grid_created or grid_updated:
        print(f"grid: {grid_created} created, {grid_updated} updated.")
    if grid.reports:
        print(f"grid reports ({len(grid.reports)}):")
        for line in grid.reports:
            print(f"  {line}")
    if world_result.skipped:
        print(f"skipped: {len(world_result.skipped)} object(s):")
        for msg in world_result.skipped:
            print(f"  {msg}")


def _run(args: argparse.Namespace) -> int:
    content_root = _require_content_root(args)
    _configure_django()
    result = _build_content(content_root)

    total = len(result.entries)
    for domain, count in sorted(result.placeholder_counts.items()):
        print(f"PLACEHOLDER remaining in {domain}/: {count}")
    if result.skipped:
        print(f"\nSkipped {len(result.skipped)} object(s):")
        for msg in result.skipped:
            print(f"  {msg}")
    if args.check:
        total_objs = sum(len(objs) for objs in result.fixtures.values())
        print(
            f"OK: {total} content files + {total_objs} fixture objects "
            f"validated; nothing written (--check)."
        )
        return 0

    written = write_fixtures(result, SRC_ROOT)
    for path in written:
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    print(f"OK: {total} content files -> {len(written)} fixture file(s).")

    if args.load:
        # Upsert path (NOT loaddata — see load_entries docstring). Sequences
        # content fixtures -> grid bundles -> deferred natural-key retry
        # (#2448) via load_world_content, rather than a bare load_entries.
        _print_load_report(_load_world(content_root))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate only; write nothing")
    parser.add_argument(
        "--load",
        action="store_true",
        help="after building, upsert into the database (requires Django env)",
    )
    parser.add_argument(
        "--content-path",
        default=None,
        help="override the content checkout location (default: CONTENT_REPO_PATH)",
    )
    args = parser.parse_args()

    try:
        return _run(args)
    except _ExitEarly as exc:
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
