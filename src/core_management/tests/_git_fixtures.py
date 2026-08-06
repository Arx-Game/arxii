"""Shared tmp-bare-origin + clone git fixture helpers for content-session tests (#3018).

Used by both the library-level session tests (``test_content_session.py``)
and the admin row-export view tests
(``web.admin.tests.test_content_row_export_views``), so the two suites can
never drift on what a "content repo checkout" fixture looks like. Never the
network, never the real lore checkout - a throwaway bare "origin" plus a
configured clone, both in a tmp dir the caller owns and cleans up.
"""

from __future__ import annotations

from pathlib import Path
import subprocess


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in ``repo``, raising on failure."""
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


def init_origin_and_clone(origin: Path, clone: Path) -> None:
    """Bare origin + a configured clone, seeded with one commit on main and pushed."""
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)], capture_output=True, check=True
    )
    subprocess.run(["git", "clone", str(origin), str(clone)], capture_output=True, check=True)
    run_git(clone, "config", "user.email", "test@example.com")
    run_git(clone, "config", "user.name", "Test")
    (clone / "README.md").write_text("# test repo\n", encoding="utf-8")
    run_git(clone, "add", ".")
    run_git(clone, "commit", "-m", "initial")
    run_git(clone, "push", "-u", "origin", "main")
