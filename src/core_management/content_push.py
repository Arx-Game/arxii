"""Commit and push exported fixtures to the private lore repo.

This is the second half of the export flow: ``export_to_content_repo``
writes fixture JSON files to the lore repo's ``fixtures/`` directory, then
``push_content_to_repo`` stages, commits, and pushes those changes to the
remote ``main`` branch.

The lore repo's ground rules are simple: history only grows, mistakes are
fixed with ``git revert``, never ``--force``. A client-side pre-push hook
blocks history rewrites. If a push is rejected (remote has commits we don't
have), this module pulls with ``--rebase`` and retries once.

Import-safe without Django configured (the tools wrapper and tests use it
standalone). All git operations use ``subprocess`` against the lore repo
checkout — never the main Arx repo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import subprocess

from core_management.content_repo import resolve_content_root

logger = logging.getLogger(__name__)

# Git identifier constants — extracted to satisfy the string-literal lint.
_GIT_TRUE = "true"
_GIT_ORIGIN = "origin"
_GIT_MAIN = "main"
_GIT_FIXTURES_PATHSPEC = "fixtures/"


class ContentPushError(Exception):
    """Raised when the content push fails."""


@dataclass
class PushResult:
    """Outcome of a push pass."""

    committed: bool = False
    pushed: bool = False
    files_staged: int = 0
    commit_sha: str = ""
    commit_message: str = ""
    rebased: bool = False
    errors: list[str] = field(default_factory=list)


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in ``repo`` and return the completed process.

    Raises ``ContentPushError`` if git exits non-zero.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise ContentPushError(
            f"git {' '.join(args)} failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )
    return result


def _is_git_repo(path: Path) -> bool:
    """Return True if ``path`` is inside a git working tree."""
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0 and result.stdout.strip() == _GIT_TRUE


def _current_branch(repo: Path) -> str:
    """Return the current branch name (or empty string for detached HEAD)."""
    result = _run_git(repo, "branch", "--show-current")
    return result.stdout.strip()


def _has_remote(repo: Path) -> bool:
    """Return True if the repo has a remote named 'origin'."""
    result = _run_git(repo, "remote")
    return _GIT_ORIGIN in result.stdout.split()


def _staged_file_count(repo: Path) -> int:
    """Return the number of files staged for commit (added/modified/deleted)."""
    result = _run_git(repo, "diff", "--cached", "--numstat")
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    return len(lines)


def _short_status(repo: Path) -> str:
    """Return a human-readable summary of working-tree changes."""
    result = _run_git(repo, "status", "--short")
    return result.stdout.strip()


def _diff_stat(repo: Path) -> str:
    """Return a ``--stat`` summary of unstaged + staged changes."""
    result = _run_git(repo, "diff", "HEAD", "--stat")
    return result.stdout.strip()


def _generate_commit_message(repo: Path) -> str:
    """Generate a commit message summarising the fixture changes."""
    stat = _diff_stat(repo)
    file_count = len([line for line in stat.splitlines() if line.strip()])
    summary = f"Update content fixtures ({file_count} file{'s' if file_count != 1 else ''})"
    body = f"\n\nExported from Arx II via `just push-content`.\n\n{stat}"
    return summary + body


def _validate_repo(root: Path) -> None:
    """Validate the lore repo is ready for push. Raises on failure."""
    if not _is_git_repo(root):
        raise ContentPushError(f"{root} is not a git repository.")

    branch = _current_branch(root)
    if branch != _GIT_MAIN:
        raise ContentPushError(
            f"Lore repo is on branch '{branch}', expected 'main'. Switch to main before pushing."
        )

    if not _has_remote(root):
        raise ContentPushError("Lore repo has no 'origin' remote configured.")


def _push_with_rebase_retry(root: Path, result: PushResult) -> None:
    """Push to origin main, pulling --rebase and retrying once on rejection."""
    try:
        _run_git(root, "push", _GIT_ORIGIN, _GIT_MAIN)
        result.pushed = True
    except ContentPushError as exc:
        logger.info("Push rejected, attempting pull --rebase: %s", exc)
        try:
            _run_git(root, "pull", "--rebase", _GIT_ORIGIN, _GIT_MAIN)
            result.rebased = True
        except ContentPushError as rebase_exc:
            result.errors.append(f"Pull --rebase failed: {rebase_exc}")
            return
        try:
            _run_git(root, "push", _GIT_ORIGIN, _GIT_MAIN)
            result.pushed = True
        except ContentPushError as retry_exc:
            result.errors.append(f"Push failed after rebase: {retry_exc}")


def push_content_to_repo(content_root: Path | None = None) -> PushResult:
    """Stage, commit, and push fixture changes in the lore repo.

    Stages all changes under ``fixtures/``, commits with an auto-generated
    message, and pushes to ``origin main``. If the push is rejected (remote
    has newer commits), pulls with ``--rebase`` and retries once.

    Returns a ``PushResult``. If there are no changes to commit, returns
    early with ``committed=False``.

    Raises ``ContentPushError`` if the repo is not a git checkout, is on
    the wrong branch, or the push fails after rebase retry.
    """
    root = content_root or resolve_content_root()
    if root is None:
        raise ContentPushError(
            "CONTENT_REPO_PATH is not set or does not exist. "
            "Set it in src/.env pointing at your local checkout of the "
            "private content repository."
        )

    _validate_repo(root)

    result = PushResult()

    # Stage all changes under fixtures/.
    fixtures_dir = root / "fixtures"
    if not fixtures_dir.is_dir():
        return result

    _run_git(root, "add", "--all", "--", _GIT_FIXTURES_PATHSPEC)

    result.files_staged = _staged_file_count(root)
    if result.files_staged == 0:
        remaining = _short_status(root)
        if remaining:
            logger.info("No staged fixture changes, but working tree has: %s", remaining)
        return result

    # Commit.
    message = _generate_commit_message(root)
    _run_git(root, "commit", "-m", message)
    result.committed = True
    result.commit_message = message

    # Get the commit SHA.
    sha_result = _run_git(root, "rev-parse", "HEAD")
    result.commit_sha = sha_result.stdout.strip()[:12]

    # Push to origin main.
    _push_with_rebase_retry(root, result)

    return result
