"""Revalidate existing migration bot heads with trusted default-branch tooling.

Dry-run by default. --publish writes the review-evidence check on each unchanged
live PR head; it never edits reports, pushes branches, or executes PR code.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from auto_rebase_migration import RefusalError, git
from closing_keywords import crowded_closing_lines, stray_references
from review_evidence_revision import is_migration_update, reviewed_revision
from validate_review_evidence import (
    REPORT_LINE,
    closing_issue_number,
    validate_pr_body,
    validate_report,
)


def gh_json(*args: str, payload: dict | None = None):
    """Call gh without shell interpolation or logging credentials."""
    command = [shutil.which("gh") or "gh", *args]
    if "--paginate" in args:
        command += ["--jq", ".[]"]
    if payload is not None:
        command += ["--input", "-"]
    try:
        result = subprocess.run(  # noqa: S603 - fixed gh executable, argv only, no shell
            command,
            input=json.dumps(payload) if payload is not None else None,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        message = f"GitHub request failed: {exc.stderr.strip()}"
        raise RuntimeError(message) from exc
    if "--paginate" in args:
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return json.loads(result.stdout)


def validate_evidence(repo: Path, repository: str, pr: dict) -> list[str]:
    """Apply the existing evidence contract with the proven original revision."""
    body = pr.get("body") or ""
    issue = closing_issue_number(body)
    if issue is None:
        return ["PR must explicitly close an issue"]
    if stray_references(body, issue) or crowded_closing_lines(body):
        return ["PR body has unsafe or crowded closing references"]
    labels = gh_json("api", f"repos/{repository}/issues/{issue}/labels", "--paginate")
    if not any(label["name"] == "review:evidence-required" for label in labels):
        return []
    errors = validate_pr_body(body)
    if "<!-- review-evidence-required -->" not in body:
        errors.append("labeled issue requires the review-evidence-required PR marker")
    report = REPORT_LINE.search(body)
    reference = (report.group(1) or report.group(2)) if report else ""
    comment = re.fullmatch(
        rf"https://github\.com/{re.escape(repository)}/(?:issues|pull)/[0-9]+#issuecomment-([0-9]+)",
        reference,
    )
    if comment is None:
        return [*errors, "recovery requires a report comment in this repository"]
    text = gh_json("api", f"repos/{repository}/issues/comments/{comment.group(1)}")["body"]
    revision = reviewed_revision(repo, pr["headRefOid"])
    print(f"Evidence revision for {pr['headRefOid']}: {revision}")
    with tempfile.TemporaryDirectory(prefix="review-report-") as directory:
        path = Path(directory) / "report.md"
        path.write_text(text, encoding="utf-8")
        errors.extend(validate_report(path, revision))
    return errors


def recover(repo: Path, repository: str, number: int, *, publish: bool) -> bool:
    """Validate a live bot head and optionally publish its exact-head result."""
    endpoint = f"repos/{repository}"
    fields = "number,title,state,isCrossRepository,baseRefName,headRefOid,body"
    pr = gh_json("pr", "view", str(number), "--repo", repository, "--json", fields)
    if pr["state"] != "OPEN" or pr["isCrossRepository"] or pr["baseRefName"] != "main":
        print(f"#{number}: skipped (not an open, same-repository PR into main)")
        return True
    git("fetch", "--quiet", "origin", f"refs/pull/{number}/head", cwd=repo)
    if git("rev-parse", "FETCH_HEAD", cwd=repo).strip() != pr["headRefOid"]:
        print(f"#{number}: head moved during fetch; rerun recovery")
        return False
    if not is_migration_update(repo, pr["headRefOid"]):
        print(f"#{number}: skipped (head is not a migration bot update)")
        return True
    try:
        errors = validate_evidence(repo, repository, pr)
    except (RefusalError, RuntimeError, subprocess.CalledProcessError) as exc:
        errors = [str(exc)]
    conclusion = "failure" if errors else "success"
    summary = (
        "\n".join(f"- {error}" for error in errors)
        if errors
        else (
            "The migration update tree was independently reproduced. The unchanged "
            "review report validates against the original pre-update evidence revision."
        )
    )
    print(f"#{number} ({pr['headRefOid']}): {conclusion}\n{summary}")
    if publish:
        live = gh_json("pr", "view", str(number), "--repo", repository, "--json", fields)
        if live != pr:
            print(f"#{number}: PR changed during validation; result not published")
            return False
        run_url = (
            f"https://github.com/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            if "GITHUB_RUN_ID" in os.environ
            else None
        )
        payload = {
            "name": "review-evidence",
            "head_sha": pr["headRefOid"],
            "status": "completed",
            "conclusion": conclusion,
            "output": {"title": "Migration evidence recovery", "summary": summary[:60000]},
        }
        if run_url:
            payload["details_url"] = run_url
        result = gh_json("api", f"{endpoint}/check-runs", "--method", "POST", payload=payload)
        print(result["html_url"])
    return not errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, action="append", help="default: all open PRs")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not args.repository or not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repository):
        parser.error("--repository owner/repo is required")
    git("fetch", "--quiet", "origin", "main", cwd=args.repo)
    numbers = args.pr
    if numbers is None:
        pulls = gh_json(
            "api", f"repos/{args.repository}/pulls?state=open&base=main&per_page=100", "--paginate"
        )
        numbers = [pr["number"] for pr in pulls]
    success = True
    for number in numbers:
        try:
            success = recover(args.repo, args.repository, number, publish=args.publish) and success
        except (RefusalError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"#{number}: recovery failed: {exc}")
            success = False
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
