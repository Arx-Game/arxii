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
import json
from pathlib import Path
import re
import subprocess

from core_management.content_export import _record_key_folded
from core_management.content_push import (
    _URL_CREDENTIALS,
    ContentPushError,
    _run_git,
)
from core_management.github_rest import GitHubRestError, github_request

SESSION_BRANCH = "content-export-session"

_GIT_ORIGIN = "origin"
_GIT_MAIN = "main"

_HTTPS_REMOTE = re.compile(r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")
_SSH_REMOTE = re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")
# ``_URL_CREDENTIALS`` (imported above) lives in ``content_push.py`` now -
# ``_run_git`` is defined there, and it is the one place a git failure
# message is actually built, so the scrub belongs where the risk originates
# rather than duplicated here (#3018 review).


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
    """Return the standard refusal text for a dirty tree on a non-session ``branch``."""
    return (
        f"working tree has uncommitted changes on '{branch}' - commit or "
        "clean them first; the session flow never stashes work."
    )


def _pending_export_refusal_message() -> str:
    """Return the refusal text for a dirty tree already on the session branch.

    A dirty tree here always means a prior row's export is still
    uncommitted/undiscarded (#3018 review) - there is no other legitimate
    way for the session branch to *become* dirty, since nothing but
    ``content_export_row`` ever writes to it outside a commit. Getting back
    out of it does not have to mean confirming or discarding that specific
    row, though - ``discard_all_pending`` (wired to the content session
    page's "Discard all pending changes" button, #3018 review) wipes
    whatever is dirty in one step, for a browser that can no longer reach the
    pending row's own diff page or simply does not want to review it.
    """
    return (
        "The content checkout has uncommitted changes from a pending export. "
        "Confirm or discard it before exporting another row."
    )


def ensure_session_branch(content_root: Path) -> None:
    """Ensure the checkout is on ``SESSION_BRANCH``, fresh off ``origin/main`` if merged.

    Fetches origin first, then refuses ANY dirty working tree - including
    when already on the session branch. This function's only caller is the
    row-export POST (``content_export_row``), which requires the tree to be
    clean by definition: enforcing that here (against git state, the only
    truth that holds across browsers/operators) is what guarantees the
    flow's core invariant, at most one pending row export at a time. Without
    this, exporting a second row while a first is still uncommitted would
    merge both rows' writes into one file, and the second row's diff/commit/
    discard would silently carry the first row's pending changes along with
    it (#3018 review - live-reproduced: two same-model exports collapsed
    into one commit under the second row's message).

    This also protects the merged-branch recreate below: a dirty session
    branch that turns out to be merged would otherwise have its uncommitted
    changes silently discarded by the detach-and-delete. If the session
    branch already exists and is fully merged into ``origin/main`` (its PR
    landed), the stale branch is deleted and recreated fresh; otherwise the
    existing branch (with its unmerged commits) is reused.
    """
    _run_git(content_root, "fetch", _GIT_ORIGIN)

    branch = _current_branch(content_root)
    dirty = _short_status_lines(content_root)
    if dirty:
        if branch == SESSION_BRANCH:
            raise ContentPushError(_pending_export_refusal_message())
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
                _run_git(content_root, "checkout", "--detach", f"{_GIT_ORIGIN}/{_GIT_MAIN}")
            _run_git(content_root, "branch", "-D", SESSION_BRANCH)
            branch_exists = False

    if branch_exists:
        if branch != SESSION_BRANCH:
            _run_git(content_root, "switch", SESSION_BRANCH)
    else:
        _run_git(content_root, "switch", "-c", SESSION_BRANCH, f"{_GIT_ORIGIN}/{_GIT_MAIN}")


#: The only two directories the row-export flow ever writes to - the sole
#: pathspecs ``discard_all_pending`` is ever allowed to touch, so it can never
#: become a bare ``git clean`` that sweeps an unrelated untracked file.
_DISCARD_PATHSPECS = ("fixtures/", "content/")


def discard_all_pending(content_root: Path) -> None:
    """Discard every uncommitted change under ``fixtures/`` and ``content/`` (#3018 review).

    The strand-recovery counterpart to a stuck pending row export: an
    operator who cannot or does not want to confirm it (a crashed browser
    mid-review, or simply changing their mind about a row) needs a way back
    to a clean working tree without hand-running git. Scoped to
    ``_DISCARD_PATHSPECS`` ONLY, always via explicit ``--`` pathspecs - never
    a bare ``git clean``, which would happily sweep an unrelated untracked
    file the operator left in the checkout for some other reason.

    ``git checkout -- <pathspec>`` errors outright if the pathspec matches no
    tracked file at all - exactly the common case for a row's first-ever
    export, which by definition never committed anything under that
    directory - so each pathspec is checked with ``git ls-files`` first and
    only passed to ``checkout`` when something tracked actually needs
    restoring. ``git clean -fd`` carries no such restriction and always runs
    for both, since an untracked leftover (the addition case) is exactly what
    it exists to remove.
    """
    to_restore = [
        pathspec
        for pathspec in _DISCARD_PATHSPECS
        if _run_git(content_root, "ls-files", "--", pathspec).stdout.strip()
    ]
    if to_restore:
        _run_git(content_root, "checkout", "--", *to_restore)
    _run_git(content_root, "clean", "-fd", "--", *_DISCARD_PATHSPECS)


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


def _json_row_present_at_head(
    content_root: Path, rel: str, key_fields: list[str], record_fields: dict
) -> bool:
    """True only if ``rel``'s ``HEAD`` copy is valid JSON containing this row's key.

    Split out of ``row_is_addition_at_head`` (ruff PLR0911) - every failure
    mode along the way (a failed ``git show``, unparseable content, an
    unexpected shape) returns ``False`` here, which that caller reads as
    "not affirmatively found" and therefore an addition (fail closed).
    """
    result = subprocess.run(
        ["git", "-C", str(content_root), "show", f"HEAD:{rel}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return False
    try:
        head_records = json.loads(result.stdout)
    except ValueError:
        return False
    if not isinstance(head_records, list):
        return False
    row_key = _record_key_folded(record_fields, key_fields)
    head_keys = {
        _record_key_folded(entry["fields"], key_fields)
        for entry in head_records
        if isinstance(entry, dict) and isinstance(entry.get("fields"), dict)
    }
    return row_key in head_keys


def row_is_addition_at_head(
    content_root: Path,
    paths: list[Path],
    key_fields: list[str] | None,
    record_fields: dict,
) -> bool:
    """Return whether a pending row export is an addition, straight from git HEAD.

    Fixes a spec hole (#3018 review): the row-export request-session record
    only ever answers for the browser that ran the export, so a second
    browser opening the same diff URL directly (or a fresh session after the
    first cleared) saw a default of ``False`` and could confirm a genuine
    addition with no new-row checkbox at all. Git state, not the request
    session, is the only truth that holds across browsers and operators - the
    same principle ``ensure_session_branch`` already applies to "is a row
    pending."

    A path not tracked at ``HEAD`` at all is unconditionally an addition - a
    file git has never seen cannot already contain this row (covers both the
    markdown case, one file per row, and a JSON fixture file's first-ever
    write). A tracked JSON fixture file can still be missing this particular
    row - ``export_single_row`` merges into a file that may hold other rows -
    so its ``HEAD`` copy is parsed and the row's folded natural key (the same
    case-insensitive comparison ``export_single_row`` itself uses) is looked
    up inside it directly.

    Fails closed on every uncertain case: no usable natural key, a ``git
    show`` failure, or content that doesn't parse as the expected JSON
    fixture shape all return ``True`` (addition) rather than ``False`` - the
    new-row checkbox is only ever skipped when the row is affirmatively
    found at ``HEAD``, never because this couldn't tell.
    """
    for path in paths:
        rel = _to_relative(content_root, [path])[0]
        if not _git_ok(content_root, "ls-files", "--error-unmatch", "--", rel):
            return True
        if not rel.endswith(".json"):
            # A tracked markdown file is one row's whole identity - being
            # tracked at HEAD already proves the row is known there.
            continue
        if key_fields is None or not _json_row_present_at_head(
            content_root, rel, key_fields, record_fields
        ):
            return True
    return False


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
