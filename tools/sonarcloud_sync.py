#!/usr/bin/env python3
"""Sync SonarCloud blockers and highs to GitHub issues. Security findings are excluded
(public repo — GitHub CodeQL handles security privately)."""

import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request

from sonarcloud_constants import (
    GH_REPO,
    SONAR_BASE,
    SONAR_ORG,
    SONAR_PROJECT,
    file_path,
    is_security,
    is_skip_path,
    severity_tier,
)

SC_KEY_MARKER = "<!-- sc:"


def fetch_issues() -> list[dict]:
    """Page through SonarCloud API and return all open issues."""
    issues: list[dict] = []
    page = 1
    while True:
        params = urllib.parse.urlencode(
            {
                "organization": SONAR_ORG,
                "componentKeys": SONAR_PROJECT,
                "resolved": "false",
                "ps": 500,
                "p": page,
            }
        )
        with urllib.request.urlopen(f"{SONAR_BASE}/issues/search?{params}") as resp:  # noqa: S310
            data = json.loads(resp.read())
        page_issues = data["issues"]
        issues.extend(page_issues)
        if len(page_issues) < 500:  # noqa: PLR2004
            break
        page += 1
    return issues


def make_title(raw: dict) -> str:
    tier = severity_tier(raw) or "unknown"
    rule = raw.get("rule", "unknown")
    msg = raw.get("message", "")[:60]
    fp = file_path(raw.get("component", ""))
    basename = fp.rsplit("/", 1)[-1] if "/" in fp else fp
    line = raw.get("line")
    location = f"{basename}:{line}" if line else basename
    title = f"[sonarcloud:{tier}] {rule}: {msg} — {location}"
    return title[:120]


def make_body(raw: dict) -> str:
    key = raw["key"]
    rule = raw.get("rule", "")
    tier = severity_tier(raw) or "unknown"
    fp = file_path(raw.get("component", ""))
    line = raw.get("line")
    location = f"`{fp}` line {line}" if line else f"`{fp}`"
    message = raw.get("message", "")
    url = f"https://sonarcloud.io/project/issues?id={SONAR_PROJECT}&open={key}"
    return (
        f"{SC_KEY_MARKER} {key} -->\n"
        f"**Rule:** `{rule}`\n"
        f"**Severity:** {tier}\n"
        f"**Location:** {location}\n\n"
        f"{message}\n\n"
        f"[View on SonarCloud]({url})\n"
    )


def parse_sc_keys(gh_issues_json: str) -> set[str]:
    """Extract embedded SonarCloud keys from the JSON of `gh issue list --json body`."""
    keys: set[str] = set()
    for issue in json.loads(gh_issues_json):
        body = issue.get("body") or ""
        for line in body.splitlines():
            if line.startswith(SC_KEY_MARKER):
                rest = line[len(SC_KEY_MARKER) :].strip()
                if rest.endswith("-->"):
                    rest = rest[:-3].strip()
                if rest:
                    keys.add(rest)
    return keys


def existing_sc_keys() -> set[str]:
    """Return all SonarCloud keys already tracked as GitHub issues (open or closed)."""
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh",
            "issue",
            "list",
            "--repo",
            GH_REPO,
            "--label",
            "sonarcloud",
            "--state",
            "all",
            "--limit",
            "2000",
            "--json",
            "body",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    keys = parse_sc_keys(result.stdout)
    if len(json.loads(result.stdout)) >= 2000:  # noqa: PLR2004
        print(
            "WARNING: gh issue list returned 2000 issues — deduplication may be incomplete.",
            file=sys.stderr,
        )
    return keys


def create_issue(raw: dict) -> None:
    title = make_title(raw)
    body = make_body(raw)
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh",
            "issue",
            "create",
            "--repo",
            GH_REPO,
            "--title",
            title,
            "--body",
            body,
            "--label",
            "sonarcloud",
        ],
        check=True,
    )
    print(f"  + {title[:90]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync SonarCloud blockers and highs to GitHub issues.",
    )
    parser.add_argument(
        "--high-limit",
        type=int,
        default=50,
        help="Max new HIGH issues to create per run (0 = unlimited, default 50)",
    )
    args = parser.parse_args()

    print("Fetching SonarCloud issues...")
    all_issues = fetch_issues()
    print(f"  {len(all_issues)} total open issues")

    qualifying = [
        raw
        for raw in all_issues
        if not is_skip_path(raw.get("component", ""))
        and not is_security(raw)
        and severity_tier(raw) is not None
    ]
    print(f"  {len(qualifying)} after filtering (skip paths, security, below-threshold severity)")

    print("Checking existing GitHub issues for deduplication...")
    skip_keys = existing_sc_keys()
    print(f"  {len(skip_keys)} SonarCloud keys already tracked — skipping")

    new_blockers = [
        r for r in qualifying if severity_tier(r) == "blocker" and r["key"] not in skip_keys
    ]
    new_highs = [r for r in qualifying if severity_tier(r) == "high" and r["key"] not in skip_keys]
    high_limit = args.high_limit or len(new_highs)

    print(f"\n{len(new_blockers)} new blocker(s), {len(new_highs)} new high(s) queued")
    if args.high_limit and len(new_highs) > args.high_limit:
        deferred = len(new_highs) - args.high_limit
        print(f"  (high limit {args.high_limit} — {deferred} highs deferred to next run)")

    created = 0
    for raw in new_blockers:
        create_issue(raw)
        created += 1
    for raw in new_highs[:high_limit]:
        create_issue(raw)
        created += 1

    print(f"\nDone: {created} issue(s) created.")


if __name__ == "__main__":
    main()
