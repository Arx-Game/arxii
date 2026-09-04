#!/usr/bin/env python3
"""Post a digest of unresolved Sentry issues to a single rolling GitHub issue.

**This repo is public, so the digest is a pointer, never a reproduction.** It
carries only Sentry's own short id, a link, the level, and counts — never the
exception message, culprit path, stack frames, or request data. A public issue
that quoted those would hand a reader a step-by-step route to the same failure;
the detail stays behind Sentry's auth, where the agent picking the work up reads
it. Anything you add to `make_body` must pass that test.

One open digest issue exists at a time: each run rewrites it in place. When
Sentry is clean the digest is *not* created, and an open one is closed.
"""

import argparse
import json
import subprocess
import sys

from sentry_constants import GH_REPO, SentryAuthError, fetch_unresolved_issues, issue_url

DIGEST_MARKER = "<!-- sentry-digest -->"
DIGEST_LABEL = "sentry"


def _day(timestamp: str | None) -> str:
    """Trim a Sentry ISO timestamp to just the date."""
    return (timestamp or "")[:10] or "-"


def make_title(issues: list[dict]) -> str:
    count = len(issues)
    noun = "issue" if count == 1 else "issues"
    return f"[sentry] {count} unresolved {noun} in production"


def make_body(issues: list[dict]) -> str:
    """Build the digest body. Pointers and counts only - see the module docstring."""
    lines = [
        DIGEST_MARKER,
        "Unresolved issues in Sentry. **Details are deliberately not copied here** "
        "(public repo) - open the link to read the message, culprit and stack.",
        "",
        "| Sentry | Level | Events | Users | First seen | Last seen |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for raw in issues:
        short_id = raw.get("shortId") or raw.get("id", "?")
        link = f"[{short_id}]({issue_url(raw['id'])})"
        lines.append(
            f"| {link} | {raw.get('level', '-')} | {raw.get('count', '-')} "
            f"| {raw.get('userCount', '-')} | {_day(raw.get('firstSeen'))} "
            f"| {_day(raw.get('lastSeen'))} |"
        )
    lines += [
        "",
        "**Working one of these:** read it in Sentry, then establish whether a fix is "
        "already in the *deployed* build before closing anything - "
        "`docs/operations/sentry-triage.md` has the check. "
        "`sentry_resolve.py <SHORT-ID>` once the fix is live; "
        "`--status resolvedInNextRelease` when it is merged but not yet deployed. "
        "Close this digest when every row is handled - the next scheduled run opens a "
        "fresh one if anything is still unresolved.",
    ]
    return "\n".join(lines)


def _gh(*args: str, check: bool = True) -> str:
    result = subprocess.run(  # noqa: S603
        ["gh", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout


def find_open_digest() -> int | None:
    """Return the number of the currently open digest issue, if any."""
    raw = _gh(
        "issue",
        "list",
        "--repo",
        GH_REPO,
        "--label",
        DIGEST_LABEL,
        "--state",
        "open",
        "--limit",
        "50",
        "--json",
        "number,body",
    )
    for issue in json.loads(raw or "[]"):
        if DIGEST_MARKER in (issue.get("body") or ""):
            return issue["number"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100, help="Max Sentry issues to list")
    parser.add_argument("--dry-run", action="store_true", help="Print the digest, touch nothing")
    args = parser.parse_args()

    try:
        issues = fetch_unresolved_issues(limit=args.limit)
    except SentryAuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Sentry reports {len(issues)} unresolved issue(s).")
    existing = find_open_digest()

    if not issues:
        # Nothing to report: never open an empty digest, and retire a stale one.
        if existing and not args.dry_run:
            _gh(
                "issue",
                "close",
                str(existing),
                "--repo",
                GH_REPO,
                "--comment",
                "Sentry is clear - no unresolved issues. Closing this digest.",
            )
            print(f"Closed stale digest #{existing}.")
        else:
            print("Nothing to do.")
        return 0

    title, body = make_title(issues), make_body(issues)
    if args.dry_run:
        print(f"\n--- {title} ---\n{body}")
        return 0

    if existing:
        _gh("issue", "edit", str(existing), "--repo", GH_REPO, "--title", title, "--body", body)
        print(f"Updated digest #{existing}.")
    else:
        url = _gh(
            "issue",
            "create",
            "--repo",
            GH_REPO,
            "--title",
            title,
            "--body",
            body,
            "--label",
            DIGEST_LABEL,
        )
        print(f"Created digest {url.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
