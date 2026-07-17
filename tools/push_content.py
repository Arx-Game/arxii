#!/usr/bin/env python3
"""Commit and push exported fixtures to the private content repo.

NOT a management command (repo rule) — a tools script wrapping
``core_management.content_push``. Stages all changes under ``fixtures/``,
commits with an auto-generated message, and pushes to ``origin main``.

Usage:
    uv run python tools/push_content.py            # commit + push
    uv run python tools/push_content.py --check    # dry-run: show what would be committed
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from core_management.content_repo import load_dotenv_content_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="dry-run: show what would be committed, commit nothing",
    )
    parser.add_argument(
        "--content-path",
        default=None,
        help="override the content checkout location (default: CONTENT_REPO_PATH)",
    )
    args = parser.parse_args()

    content_path = args.content_path or load_dotenv_content_path()
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

    if args.check:
        return _run_check(content_root)

    from core_management.content_push import (  # noqa: PLC0415
        ContentPushError,
        push_content_to_repo,
    )

    try:
        result = push_content_to_repo(content_root)
    except ContentPushError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not result.committed:
        print("No changes to commit.")
        return 0

    print(f"Committed {result.files_staged} file(s): {result.commit_sha}")
    if result.rebased:
        print("Rebased on top of remote changes.")
    if result.pushed:
        print("Pushed to origin main.")
    else:
        print("Push FAILED — see errors below.", file=sys.stderr)
    for err in result.errors:
        print(f"  {err}", file=sys.stderr)
    return 0 if result.pushed else 1


def _run_check(content_root: Path) -> int:
    """Dry-run: show git status/diff without committing."""
    from core_management.content_push import (  # noqa: PLC0415
        _current_branch,
        _diff_stat,
        _is_git_repo,
        _short_status,
    )

    if not _is_git_repo(content_root):
        print(f"Error: {content_root} is not a git repository.", file=sys.stderr)
        return 1

    print(f"Branch: {_current_branch(content_root)}")

    status = _short_status(content_root)
    if not status:
        print("No changes to commit.")
        return 0

    print(f"\nChanges:\n{status}")

    diff = _diff_stat(content_root)
    if diff:
        print(f"\nDiff stat:\n{diff}")

    print("\nNothing committed (--check).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
