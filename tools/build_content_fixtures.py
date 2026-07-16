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
    build_all,
    write_fixtures,
)


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


def _load_dotenv_path() -> str | None:
    """Read CONTENT_REPO_PATH from the environment, falling back to src/.env."""
    value = os.environ.get("CONTENT_REPO_PATH")
    if value:
        return value
    env_file = SRC_ROOT / ".env"
    if env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("CONTENT_REPO_PATH="):
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _require_content_root(args: argparse.Namespace) -> Path:
    """Resolve + validate the content checkout path, or raise ``_ExitEarly(2)``."""
    content_path = args.content_path or _load_dotenv_path()
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


def _load_content(result) -> tuple[int, int]:
    """Run ``load_entries``, or raise ``_ExitEarly`` with a clean stderr message."""
    from django.db import Error as DjangoDbError  # noqa: PLC0415

    from core_management.content_fixtures import load_entries  # noqa: PLC0415

    try:
        return load_entries(result)
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
        # Upsert path (NOT loaddata — see load_entries docstring).
        created, updated = _load_content(result)
        print(f"loaded: {created} created, {updated} updated.")
        if result.skipped:
            print(f"skipped: {len(result.skipped)} object(s) (see above).")
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
