"""Find GitHub closing keywords aimed at the wrong issue (#4903).

GitHub closes the issue or PR named right after close/closes/closed, fix/fixes/fixed
or resolve/resolves/resolved when that text lands on main: a squash commit message,
or a PR body at merge. On 2026-11-01 the prose "the bot fixed #4866" in a commit body
closed ApostateCD's open PR #4866, unmerged, the moment #4899 merged.

Used by the commit-msg hook (tools/githooks/commit-msg) with the branch's issue as
the one allowed target, and by spec-evidence.yml on the PR body with the PR's own
``Closes #N``. Standard library only, so the hook runs without a venv.

    python3 tools/closing_keywords.py commit-msg <message-file>
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

# Each keyword covers only the reference straight after it: "fixed #1 and #2" closes #1.
STRAY = re.compile(
    r"\b(?P<phrase>(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+"
    r"(?:(?:[\w.-]+/[\w.-]+)?#|https://github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/)"
    r"(?P<number>\d+))",
    re.IGNORECASE,
)
# Branches carry their issue number: chore-4903-..., feature-4813-..., fix/4506-...
_BRANCH_ISSUE = re.compile(r"(?:^|[-/])(\d{2,})(?:-|$)")
_SCISSORS = "# ------------------------ >8 ------------------------"


# What may sit beside closing references on a deliberate closing line: a list bullet,
# separators, "and". Anything else on the line makes it prose.
_CLOSING_LINE_FILLER = re.compile(r"^[\s,;.&*-]*(?:and[\s,;.&]*)*$", re.IGNORECASE)


# A labelled close: "- Fixes #3679: hub models are blind ..." (colon straight after it).
_LABELLED_CLOSE = re.compile(r"^\s*(?:[-*]\s+)?" + STRAY.pattern + r":\s", re.IGNORECASE)


def _is_closing_line(line: str) -> bool:
    """A deliberate close: a line of nothing but closing references, or a labelled one.

    `Closes #1`, `Closes #1, closes #2`, `- Fixes #3679: what it fixes`. Not a sentence
    that happens to hold a keyword: "Do not close #3751" closed #3751 (#3955).
    """
    if not STRAY.search(line):
        return False
    return bool(_CLOSING_LINE_FILLER.match(STRAY.sub("", line)) or _LABELLED_CLOSE.match(line))


def stray_references(text: str, allowed: str | None) -> list[str]:
    """Closing-keyword phrases in ``text`` that read as prose rather than a deliberate close.

    A reference is deliberate when it names ``allowed`` (the PR's or branch's own issue)
    or stands on a line of nothing but closing references, the way a PR closing several
    SonarCloud issues lists them (#4772, #4492). It is prose otherwise, which is how both
    accidents happened: "the bot ... #4866" closed an open PR (#4899), and "Close #4684
    only after every current row ..." closed a Sentry issue the line said to keep open
    (#4721).
    """
    return [
        m["phrase"]
        for line in text.splitlines()
        if not _is_closing_line(line)
        for m in STRAY.finditer(line)
        if m["number"] != allowed
    ]


def message_text(raw: str) -> str:
    """The commit message as git will record it: no comment lines, nothing past scissors."""
    kept = []
    for line in raw.splitlines():
        if line == _SCISSORS:
            break
        if not line.startswith("#"):
            kept.append(line)
    return "\n".join(kept)


def branch_issue(branch: str) -> str | None:
    match = _BRANCH_ISSUE.search(branch)
    return match.group(1) if match else None


def _git(*args: str) -> str:
    proc = subprocess.run(  # noqa: S603 - fixed argv
        ["git", *args],  # noqa: S607 - git on PATH
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _current_branch() -> str:
    """The branch being committed to, also mid-rebase, when HEAD is detached.

    symbolic-ref, not rev-parse --abbrev-ref: it names the branch before a first
    commit. A `reword` or `squash` in `git rebase -i` runs this hook with HEAD
    detached; git keeps the branch being rebased in rebase-merge/ (or rebase-apply/).
    """
    branch = _git("symbolic-ref", "--quiet", "--short", "HEAD")
    if branch:
        return branch
    for state in ("rebase-merge", "rebase-apply"):
        head_name = Path(_git("rev-parse", "--git-path", f"{state}/head-name") or "/nonexistent")
        if head_name.is_file():
            return head_name.read_text(encoding="utf-8").strip().removeprefix("refs/heads/")
    return ""


def check_commit_message(path: str) -> int:
    text = message_text(Path(path).read_text(encoding="utf-8"))
    allowed = branch_issue(_current_branch())
    found = stray_references(text, allowed)
    if not found:
        return 0
    target = f"#{allowed}, this branch's issue" if allowed else "nothing (no issue in the name)"
    print("Commit rejected: GitHub closes what a closing keyword names (#4903).", file=sys.stderr)
    for phrase in found:
        print(f"  {phrase!r}", file=sys.stderr)
    print(
        f"On this branch a closing keyword may name {target}. Reword the rest, e.g.\n"
        "'the bot renumbered #4866' or 'on #4866', not 'fixed #4866'.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "commit-msg":  # noqa: PLR2004 - mode + file
        return check_commit_message(argv[1])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
