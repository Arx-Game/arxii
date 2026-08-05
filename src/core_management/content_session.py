"""Row-level content export session: a single git branch as scratch space (#3018).

This is additive beside ``content_push.py``'s ``push_content_to_repo``, which
stays a main-only, whole-corpus flow. A content session lets staff export one
row at a time from the admin, review each row's diff, and later bundle the
accumulated commits into a single pull request for review - the branch *is*
the session state. There is no separate database table tracking which rows
are "in" a pending export; ``git log`` and ``git diff`` against
``origin/main`` are the source of truth, queried fresh on every call.

All git plumbing reuses ``content_push._run_git``/``ContentPushError`` so
error formatting matches the rest of the export pipeline. The one HTTP call
this module makes - opening the session's pull request - goes through the
shared ``github_rest`` client.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from core_management.content_push import ContentPushError, _run_git
from core_management.github_rest import GitHubRestError, github_request

SESSION_BRANCH = "content-export-session"

_GIT_ORIGIN = "origin"
_GIT_MAIN = "main"

_HTTPS_REMOTE = re.compile(r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")
_SSH_REMOTE = re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")
# Strips a userinfo/credential segment (user:token@ or token@) from a URL
# before it ever reaches an error message - an https remote can carry one.
_URL_CREDENTIALS = re.compile(r"//[^/@]+@")


@dataclass
class SessionState:
    """Snapshot of the session branch's state, relative to ``origin/main``."""

    branch: str
    on_session: bool
    commits: list[str]
    diff_stat: str
    dirty: list[str]


def _git_ok(repo: Path, *args: str) -> bool:
    """Run a git command in ``repo``, returning True on exit 0 without raising."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode == 0


def _current_branch(repo: Path) -> str:
    """Return the current branch name (or empty string for detached HEAD)."""
    return _run_git(repo, "branch", "--show-current").stdout.strip()


def _short_status_lines(repo: Path) -> list[str]:
    """Return non-empty ``git status --short`` lines."""
    result = _run_git(repo, "status", "--short")
    return [line for line in result.stdout.splitlines() if line.strip()]


def _to_relative(repo: Path, paths: list[Path]) -> list[str]:
    """Return ``paths`` as strings relative to ``repo``."""
    rels: list[str] = []
    for path in paths:
        candidate = Path(path)
        if candidate.is_absolute():
            rels.append(str(candidate.relative_to(repo)))
        else:
            rels.append(str(candidate))
    return rels


def _dirty_refusal_message(branch: str) -> str:
    """Return the standard refusal text for a dirty tree on ``branch``."""
    return (
        f"working tree has uncommitted changes on '{branch}' - commit or "
        "clean them first; the session flow never stashes work."
    )


def ensure_session_branch(content_root: Path) -> None:
    """Ensure the checkout is on ``SESSION_BRANCH``, fresh off ``origin/main`` if merged.

    Fetches origin first. If the working tree is dirty, raises
    ``ContentPushError`` without touching anything else - the session flow
    never stashes work. This applies on any branch, including the session
    branch itself: a dirty session branch that turns out to be merged would
    otherwise have its uncommitted changes silently discarded by the
    detach-and-delete recreate below. If the session branch already exists
    and is fully merged into ``origin/main`` (its PR landed), the stale
    branch is deleted and recreated fresh; otherwise the existing branch
    (with its unmerged commits) is reused.
    """
    _run_git(content_root, "fetch", _GIT_ORIGIN)

    branch = _current_branch(content_root)
    dirty = _short_status_lines(content_root)
    if dirty and branch != SESSION_BRANCH:
        raise ContentPushError(_dirty_refusal_message(branch))

    branch_exists = _git_ok(
        content_root, "show-ref", "--verify", "--quiet", f"refs/heads/{SESSION_BRANCH}"
    )
    if branch_exists:
        merged = _git_ok(
            content_root,
            "merge-base",
            "--is-ancestor",
            SESSION_BRANCH,
            f"{_GIT_ORIGIN}/{_GIT_MAIN}",
        )
        if merged:
            if branch == SESSION_BRANCH:
                if dirty:
                    raise ContentPushError(_dirty_refusal_message(branch))
                _run_git(content_root, "checkout", "--detach", f"{_GIT_ORIGIN}/{_GIT_MAIN}")
            _run_git(content_root, "branch", "-D", SESSION_BRANCH)
            branch_exists = False

    if branch_exists:
        if branch != SESSION_BRANCH:
            _run_git(content_root, "switch", SESSION_BRANCH)
    else:
        _run_git(content_root, "switch", "-c", SESSION_BRANCH, f"{_GIT_ORIGIN}/{_GIT_MAIN}")


def commit_row_export(content_root: Path, paths: list[Path], message: str) -> str:
    """Stage exactly ``paths`` and commit them; return the short commit sha.

    Any other dirty file in the working tree is left uncommitted.
    """
    rels = _to_relative(content_root, paths)
    _run_git(content_root, "add", "--", *rels)
    _run_git(content_root, "commit", "-m", message)
    return _run_git(content_root, "rev-parse", "--short", "HEAD").stdout.strip()


def discard_row_export(content_root: Path, paths: list[Path]) -> None:
    """Discard uncommitted changes to ``paths`` - restore tracked, delete new."""
    for rel in _to_relative(content_root, paths):
        if _git_ok(content_root, "ls-files", "--error-unmatch", "--", rel):
            _run_git(content_root, "checkout", "--", rel)
        else:
            (content_root / rel).unlink(missing_ok=True)


def _session_commits(content_root: Path) -> list[str]:
    """Return one-line ``sha subject`` entries for commits on the session branch not on main."""
    result = _run_git(content_root, "log", "--oneline", f"{_GIT_ORIGIN}/{_GIT_MAIN}..HEAD")
    return [line for line in result.stdout.splitlines() if line.strip()]


def session_state(content_root: Path) -> SessionState:
    """Return the current session branch's state relative to ``origin/main``."""
    branch = _current_branch(content_root)
    diff_stat = _run_git(
        content_root, "diff", f"{_GIT_ORIGIN}/{_GIT_MAIN}...HEAD", "--stat"
    ).stdout.strip()
    return SessionState(
        branch=branch,
        on_session=branch == SESSION_BRANCH,
        commits=_session_commits(content_root),
        diff_stat=diff_stat,
        dirty=_short_status_lines(content_root),
    )


def _no_index_diff(content_root: Path, rel: str) -> str:
    """Return a full-file addition diff for one untracked path (#3018).

    Plain ``git diff`` only compares tracked content, so a brand-new export
    (the common row-export case: a row's first commit into the corpus) is
    invisible to it - the working tree file exists but the diff renders
    empty. ``git diff --no-index`` against ``/dev/null`` shows the whole file
    as an addition instead, without touching the index. Exit 1 is the normal
    "a difference exists" result for ``--no-index``; only other nonzero
    exits are a real git failure.
    """
    result = subprocess.run(
        ["git", "-C", str(content_root), "diff", "--no-index", "--", "/dev/null", rel],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode not in (0, 1):
        raise ContentPushError(
            f"git diff --no-index failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )
    return result.stdout


def row_diff(content_root: Path, paths: list[Path]) -> str:
    """Return the uncommitted diff (working tree vs HEAD) for ``paths``.

    Tracked paths go through plain ``git diff``; untracked ones (a row's
    first-ever export, before it has any commit) go through
    ``_no_index_diff`` instead - see that helper's docstring for why plain
    ``git diff`` cannot show them.
    """
    rels = _to_relative(content_root, paths)
    tracked = [
        rel for rel in rels if _git_ok(content_root, "ls-files", "--error-unmatch", "--", rel)
    ]
    untracked = [rel for rel in rels if rel not in tracked]
    parts: list[str] = []
    if tracked:
        parts.append(_run_git(content_root, "diff", "--", *tracked).stdout)
    parts.extend(_no_index_diff(content_root, rel) for rel in untracked)
    return "".join(parts)


def session_diff(content_root: Path) -> str:
    """Return the full session diff, ``origin/main...HEAD``."""
    return _run_git(content_root, "diff", f"{_GIT_ORIGIN}/{_GIT_MAIN}...HEAD").stdout


def _remote_slug(content_root: Path) -> tuple[str, str]:
    """Return ``(owner, repo)`` parsed from the origin remote URL.

    Handles both ``https://github.com/O/R(.git)`` and ``git@github.com:O/R(.git)``.
    Raises ``ContentPushError`` for anything else.
    """
    url = _run_git(content_root, "remote", "get-url", _GIT_ORIGIN).stdout.strip()
    for pattern in (_HTTPS_REMOTE, _SSH_REMOTE):
        match = pattern.match(url)
        if match:
            return match.group("owner"), match.group("repo")
    safe_url = _URL_CREDENTIALS.sub("//", url)
    raise ContentPushError(
        f"origin remote URL is not a GitHub URL this session flow parses: {safe_url}"
    )


def open_session_pr(content_root: Path, *, title: str, body: str) -> str:
    """Push the session branch and open (or reuse) its pull request; return the html_url.

    Reuses an already-open PR for the session branch instead of filing a
    duplicate on repeated calls.
    """
    owner, repo = _remote_slug(content_root)
    slug = f"{owner}/{repo}"
    _run_git(content_root, "push", "-u", _GIT_ORIGIN, SESSION_BRANCH)
    try:
        existing = github_request(
            "GET", f"/repos/{slug}/pulls?head={owner}:{SESSION_BRANCH}&state=open"
        )
        if existing:
            return existing[0]["html_url"]
        created = github_request(
            "POST",
            f"/repos/{slug}/pulls",
            payload={"title": title, "body": body, "head": SESSION_BRANCH, "base": _GIT_MAIN},
        )
    except GitHubRestError as exc:
        raise ContentPushError(f"could not open the session pull request: {exc}") from exc
    if not isinstance(created, dict):
        raise ContentPushError("GitHub returned an unexpected response shape for the new PR.")
    return created["html_url"]
