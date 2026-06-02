#!/usr/bin/env python3
"""Bulk-mark SonarCloud issues as falsepositive or wontfix via the write API.
Requires SONAR_TOKEN env var (generate at sonarcloud.io → My Account → Security).

Example — dry-run all hard-coded-password findings in test files:
    python tools/sonarcloud_triage.py --rule python:S2068 --path "*/tests/*" --dry-run

Example — apply:
    python tools/sonarcloud_triage.py --rule python:S2068 --path "*/tests/*"
"""

import argparse
import base64
import fnmatch
import json
import os
import sys
import urllib.parse
import urllib.request

from sonarcloud_constants import SONAR_BASE, SONAR_ORG, SONAR_PROJECT, file_path

VALID_TRANSITIONS = ("falsepositive", "wontfix")


def matches_rule(raw: dict, rule: str | None) -> bool:
    if not rule:
        return True
    return raw.get("rule", "") == rule


def matches_path(raw: dict, path_pattern: str | None) -> bool:
    if not path_pattern:
        return True
    fp = file_path(raw.get("component", ""))
    return fnmatch.fnmatch(fp, path_pattern)


def _sonar_headers() -> dict[str, str]:
    token = os.environ.get("SONAR_TOKEN", "")
    if not token:
        print("ERROR: SONAR_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    credentials = base64.b64encode(f"{token}:".encode()).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _fetch_all_issues() -> list[dict]:
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


def _do_transition(issue_key: str, transition: str, headers: dict[str, str]) -> None:
    body = urllib.parse.urlencode({"issue": issue_key, "transition": transition}).encode()
    req = urllib.request.Request(  # noqa: S310
        f"{SONAR_BASE}/issues/do_transition",
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        resp.read()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-mark SonarCloud issues as false positive or won't-fix.",
    )
    parser.add_argument("--rule", help="Rule key to target (e.g. python:S2068)")
    parser.add_argument("--path", dest="path_pattern", help="File path glob (e.g. '*/tests/*')")
    parser.add_argument("--transition", default="falsepositive", choices=VALID_TRANSITIONS)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would change without calling the API"
    )
    args = parser.parse_args()

    if not args.rule and not args.path_pattern:
        print(
            "ERROR: provide at least --rule or --path to avoid triaging every open issue.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Fetching SonarCloud issues...")
    all_issues = _fetch_all_issues()
    print(f"  {len(all_issues)} open issues")

    targets = [
        raw
        for raw in all_issues
        if matches_rule(raw, args.rule) and matches_path(raw, args.path_pattern)
    ]
    print(f"  {len(targets)} match filter(s)")

    if not targets:
        print("Nothing to do.")
        return

    headers = {} if args.dry_run else _sonar_headers()

    prefix = "[DRY RUN] Would mark" if args.dry_run else f"Marking as '{args.transition}'"
    print(f"\n{prefix}:")
    for raw in targets:
        fp = file_path(raw.get("component", ""))
        line = raw.get("line", "?")
        print(f"  {raw['key']}  {raw.get('rule', '')}  {fp}:{line}")
        if not args.dry_run:
            _do_transition(raw["key"], args.transition, headers)

    if args.dry_run:
        print(f"\n[DRY RUN] {len(targets)} issue(s) would be marked '{args.transition}'.")
        print("Re-run without --dry-run to apply.")
    else:
        print(f"\nDone: {len(targets)} issue(s) marked '{args.transition}'.")


if __name__ == "__main__":
    main()
