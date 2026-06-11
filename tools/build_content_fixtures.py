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
    ContentError,
    build_all,
    write_fixtures,
)


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

    content_path = args.content_path or _load_dotenv_path()
    if not content_path:
        print(
            "CONTENT_REPO_PATH is not set. Add it to src/.env pointing at your "
            "local checkout of the private content repository.",
            file=sys.stderr,
        )
        return 2
    content_root = Path(content_path).expanduser()
    if not content_root.is_dir():
        print(f"Content path does not exist: {content_root}", file=sys.stderr)
        return 2

    try:
        result = build_all(content_root)
    except ContentError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    total = len(result.entries)
    for domain, count in sorted(result.placeholder_counts.items()):
        print(f"PLACEHOLDER remaining in {domain}/: {count}")
    if args.check:
        print(f"OK: {total} content files validated; nothing written (--check).")
        return 0

    written = write_fixtures(result, SRC_ROOT)
    for path in written:
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    print(f"OK: {total} content files -> {len(written)} fixture file(s).")

    if args.load:
        # Upsert path (NOT loaddata — see load_entries docstring). Needs the
        # Django env; settings resolve .env relative to src/.
        import django  # noqa: PLC0415

        os.chdir(SRC_ROOT)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
        django.setup()
        from core_management.content_fixtures import load_entries  # noqa: PLC0415

        created, updated = load_entries(result)
        print(f"loaded: {created} created, {updated} updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
