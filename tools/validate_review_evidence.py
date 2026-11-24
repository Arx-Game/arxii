"""Validate committed review evidence required before opening a pull request."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

_SHA = re.compile(r"^[0-9a-f]{40}$")
_PLACEHOLDER = re.compile(r"(?:TBD|TODO|FILL[- ]?ME|<[^>]+>)", re.IGNORECASE)
_STATUSES = {"PASS", "FAIL", "BLOCKED", "OUT_OF_SCOPE"}
_REQUIRED_FIELDS = (
    "Reviewed revision",
    "Reviewer",
    "Reviewer verdict",
    "Application/build identity",
    "Environment",
    "Viewports/themes",
    "Approved design",
    "Visual review",
    "Visual verdict",
    "Screenshots",
    "Comparison notes",
    "Tested interactions",
    "Fixture/live boundary",
    "Overall outcome",
)
_LEDGER_COLUMNS = 4
_LISTED_SCREENS = 5
# A report or body that links more images than one `just shot-post` call can post
# is refused rather than fetched one by one on the runner (#5310).
_MAX_CHECKED_URLS = 20
_UNRESOLVED_HEADING = "## unresolved findings"
_ISSUE_LINK = re.compile(r"^(Refs|Closes)\s+#([0-9]+)\.?\s*$", re.MULTILINE)
# `^` (not `\A`) so the line can appear anywhere in the body, not only as the
# very first character — the requirement is that the PR names its closing
# issue, not that it leads with it (#3938).
_CLOSING_ISSUE_LINK = re.compile(r"^Closes\s+#([0-9]+)\.?\s*$", re.MULTILINE)
_DEPENDABOT_LOGINS = frozenset({"dependabot[bot]", "dependabot-preview[bot]"})
# The PR body's report reference: a backtick-wrapped repository path, or a bare
# https URL. The review-evidence workflow imports this rather than copying it.
REPORT_LINE = re.compile(r"^- Report: (?:`([^`]+)`|(https://\S+))$", re.MULTILINE)
# A chore or dependency PR that closes no issue says why on a line of its own (#5310).
_NO_ISSUE_LINE = re.compile(r"^No issue:\s*(.+)$", re.MULTILINE)
# A frontend PR that changes no screen says so instead of attaching a picture (#5310).
_NO_VISUAL_CHANGE_LINE = re.compile(r"^No visual change:\s*(.+)$", re.MULTILINE)
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\((https://[^)\s]+)\)")
_HTML_IMAGE = re.compile(r"<img\b[^>]*\bsrc=\"(https://[^\"]+)\"", re.IGNORECASE)
# Hosts where GitHub stores images dragged into a comment or PR body.
_GITHUB_ATTACHMENT_HOSTS = (
    "https://github.com/user-attachments/",
    "https://user-images.githubusercontent.com/",
    "https://private-user-images.githubusercontent.com/",
)


def linked_issue_number(body: str) -> str | None:
    """Return the first workflow issue reference in a PR body, if present.

    The evidence workflow is opt-in through a label on this linked issue.
    Unlinked PRs, including dependency updates, therefore have no evidence
    requirement to evaluate.
    """
    match = _ISSUE_LINK.search(body)
    return match.group(2) if match else None


def closing_issue_number(body: str) -> str | None:
    """Return the first issue that the PR body explicitly closes."""
    match = _CLOSING_ISSUE_LINK.search(body)
    return match.group(1) if match else None


def is_dependabot_login(login: str | None) -> bool:
    """Return whether a pull-request author is a Dependabot account."""
    return login in _DEPENDABOT_LOGINS


def _stated_reason(body: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(body)
    if not match:
        return None
    reason = match.group(1).strip()
    return reason if _usable(reason) else None


def no_issue_reason(body: str) -> str | None:
    """Return the reason a chore or dependency PR closes no issue, if it states one (#5310)."""
    return _stated_reason(body, _NO_ISSUE_LINE)


def no_visual_change_reason(body: str) -> str | None:
    """Return the reason a frontend PR carries no screenshot, if it states one (#5310)."""
    return _stated_reason(body, _NO_VISUAL_CHANGE_LINE)


def hosted_image_urls(body: str, repository: str) -> list[str]:
    """Return the images in a PR body that GitHub hosts for this repository.

    Only these count as evidence of what a screen looks like: a badge from a bot
    or an outside host is an image too, and the SonarCloud comment carries one.
    """
    urls = _MARKDOWN_IMAGE.findall(body) + _HTML_IMAGE.findall(body)
    return [url for url in urls if is_hosted_image_url(url, repository)]


def is_hosted_image_url(url: str, repository: str) -> bool:
    """Return whether GitHub hosts this image for this repository.

    CI fetches only these: a report comes from a comment anyone can write, so an
    unfiltered fetch would let a commenter point the runner anywhere.
    """
    own_raw = f"https://raw.githubusercontent.com/{repository}/"
    return url.startswith((own_raw, *_GITHUB_ATTACHMENT_HOSTS))


def unreachable_images(urls: list[str], timeout: float = 15.0) -> list[str]:
    """Return each URL that does not answer with an image.

    It asks for the first byte with GET rather than HEAD: a signed attachment URL is
    signed for one method and can refuse a HEAD.
    """
    if len(urls) > _MAX_CHECKED_URLS:
        return [f"{len(urls)} images; at most {_MAX_CHECKED_URLS} are checked"]
    failures: list[str] = []
    for url in urls:
        request = urllib.request.Request(url, headers={"Range": "bytes=0-0"})  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                kind = response.headers.get("Content-Type", "")
                ok = response.status in {HTTPStatus.OK, HTTPStatus.PARTIAL_CONTENT}
                if not ok or not kind.startswith("image/"):
                    failures.append(f"{url} ({response.status}, {kind or 'no type'})")
        except (urllib.error.URLError, TimeoutError) as error:
            failures.append(f"{url} ({error})")
    return failures


def frontend_screenshot_errors(body: str, changed: list[str], repository: str) -> list[str]:
    """Return errors when a PR changes a screen and shows no picture of it (#5310).

    A change to non-test ``frontend/src/**/*.tsx`` needs an image hosted on GitHub
    in the PR body, or a ``No visual change: <reason>`` line.
    """
    screens = [path for path in changed if is_screen_file(path)]
    if not screens:
        return []
    if no_visual_change_reason(body) is not None:
        return []
    images = hosted_image_urls(body, repository)
    if not images:
        listed = ", ".join(screens[:_LISTED_SCREENS])
        if len(screens) > _LISTED_SCREENS:
            listed += " ..."
        return [
            f"this PR changes screen code ({listed}) and its body shows no screenshot. "
            "Take one with `just shot` and post it with `just shot-post`, then paste the "
            "printed Markdown into the PR body; or add a line "
            "`No visual change: <reason>`."
        ]
    return [f"screenshot does not load: {failure}" for failure in unreachable_images(images)]


def is_screen_file(path: str) -> bool:
    """Return whether a changed path is frontend screen code rather than a test."""
    if not path.startswith("frontend/src/") or not path.endswith(".tsx"):
        return False
    if path.startswith("frontend/src/test/") or "/__tests__/" in path:
        return False
    return not path.endswith((".test.tsx", ".spec.tsx", ".stories.tsx"))


def _field(lines: list[str], label: str) -> str:
    prefix = f"- {label}:"
    for line in lines:
        if line.strip().startswith(prefix):
            return line.strip()[len(prefix) :].strip()
    return ""


def _usable(value: str) -> bool:
    return bool(value) and not _PLACEHOLDER.search(value)


def validate_pr_body(body: str, expected_issue: str | None = None) -> list[str]:
    """Return errors when a PR body omits the closing-issue evidence contract."""
    errors: list[str] = []
    closing_issue = closing_issue_number(body)
    if closing_issue is None:
        errors.append("PR body must include a line of the form Closes #<number>")
    elif expected_issue and closing_issue != expected_issue:
        errors.append(f"PR body closes issue #{closing_issue}, expected #{expected_issue}")
    if REPORT_LINE.search(body) is None:
        errors.append("PR body is missing the committed review report link")
    if "## Review evidence" not in body:
        errors.append("PR body is missing the Review evidence section")
    return errors


def _validate_ledger_row(cells: list[str]) -> list[str]:
    if len(cells) != _LEDGER_COLUMNS:
        return [f"ledger row has {len(cells)} columns"]
    criterion, status, evidence, decision = cells
    errors: list[str] = []
    if not criterion or not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", criterion):
        errors.append(f"invalid criterion id: {criterion or '(empty)'}")
    status = status.upper()
    if status not in _STATUSES:
        errors.append(f"{criterion or 'criterion'} has invalid status {status!r}")
    if not _usable(evidence) and status != "OUT_OF_SCOPE":
        errors.append(f"{criterion or 'criterion'} needs concrete evidence")
    if status == "OUT_OF_SCOPE" and not _usable(decision):
        errors.append(f"{criterion or 'criterion'} needs an authorized out-of-scope decision")
    return errors


def _ledger_rows(lines: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    statuses: list[str] = []
    header = "|id|status|evidence|authorizeddecision|"
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().lower().replace(" ", "") == header
        ),
        None,
    )
    if header_index is None:
        return ["requirement ledger table is missing"], statuses
    for line in lines[header_index + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if statuses:
                break
            continue
        if re.match(r"^\|\s*:?-+", stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        errors.extend(_validate_ledger_row(cells))
        if len(cells) == _LEDGER_COLUMNS:
            statuses.append(cells[1].upper())
    if not statuses:
        errors.append("requirement ledger has no rows")
    return errors, statuses


def _validate_fields(fields: dict[str, str], expected_revision: str | None) -> list[str]:
    errors = [
        f"missing or placeholder field: {label}"
        for label, value in fields.items()
        if not _usable(value)
    ]
    revision = fields["Reviewed revision"].strip("`")
    if not _SHA.fullmatch(revision):
        errors.append("Reviewed revision must be a 40-character commit SHA")
    if expected_revision and revision != expected_revision:
        errors.append(
            "report revision "
            f"{revision!r} does not match the reviewed code revision {expected_revision}"
        )
    if fields["Reviewer verdict"].strip(" `").upper() != "PASS":
        errors.append("reviewer verdict must be PASS before opening a PR")
    if fields["Overall outcome"].strip(" `").upper() != "PASS":
        errors.append("overall outcome must be PASS before opening a PR")
    return errors


def _validate_screenshot_refs(screenshots: str, *, repository: str | None = None) -> list[str]:
    errors: list[str] = []
    image_refs = re.findall(r"!\[[^]]*\]\(([^)]+)\)", screenshots)
    if not image_refs:
        return ["screenshots must include at least one Markdown image"]
    if repository:
        urls = [reference for reference in image_refs if reference.startswith("https://")]
        foreign = [url for url in urls if not is_hosted_image_url(url, repository)]
        errors.extend(
            f"screenshot is not hosted by GitHub for this repository: {url}" for url in foreign
        )
        hosted = [url for url in urls if url not in foreign]
        errors.extend(f"screenshot does not load: {bad}" for bad in unreachable_images(hosted))
    for reference in image_refs:
        if reference.startswith(("http://", "https://")):
            continue
        image_path = Path(reference)
        if image_path.is_absolute() or ".." in image_path.parts:
            errors.append(f"screenshot path must be repository-relative: {reference}")
        elif not (Path.cwd() / image_path).is_file():
            errors.append(f"screenshot file does not exist: {reference}")
        elif image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            errors.append(f"screenshot is not an image file: {reference}")
    return errors


def _validate_visual_checklist_row(cells: list[str]) -> list[str]:
    if len(cells) != _LEDGER_COLUMNS:
        return ["Visual checklist rows must have four columns"]
    element, expected, result, evidence = cells
    errors: list[str] = []
    if not _usable(element) or not _usable(expected) or not _usable(evidence):
        errors.append("Visual checklist rows need concrete element, expected, and evidence values")
    if result.upper() != "MATCH":
        errors.append(f"visual checklist item {element or '(empty)'} is not marked MATCH")
    return errors


def _validate_visual_checklist(lines: list[str]) -> list[str]:
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().lower() == "## visual checklist"
        ),
        None,
    )
    if start is None:
        return ["completed visual review requires a Visual checklist section"]
    header = "|element|expected|result|evidence|"
    header_index = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].strip().lower().replace(" ", "") == header
        ),
        None,
    )
    if header_index is None:
        return ["Visual checklist must have Element, Expected, Result, and Evidence columns"]
    errors: list[str] = []
    rows = 0
    for line in lines[header_index + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        if re.match(r"^\|\s*:?-+", stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        errors.extend(_validate_visual_checklist_row(cells))
        rows += len(cells) == _LEDGER_COLUMNS
    if not rows:
        errors.append("Visual checklist has no rows")
    return errors


def _validate_visual_fields(
    fields: dict[str, str], lines: list[str], *, repository: str | None = None
) -> list[str]:
    visual = fields["Visual review"].lower()
    verdict = fields["Visual verdict"].strip(" `").upper()
    screenshots = fields["Screenshots"]
    if "not applicable" in visual:
        if verdict != "NOT_APPLICABLE":
            return ["non-visual review must use Visual verdict: NOT_APPLICABLE"]
        return []
    errors = []
    if verdict != "PASS":
        errors.append("completed visual review must have Visual verdict: PASS")
    if not _usable(screenshots) or "not applicable" in screenshots.lower():
        errors.append("completed visual review requires actual screenshot paths or URLs")
    if _PLACEHOLDER.search(screenshots):
        errors.append("screenshot field contains a placeholder")
    errors.extend(_validate_screenshot_refs(screenshots, repository=repository))
    errors.extend(_validate_visual_checklist(lines))
    return errors


def _validate_unresolved(lines: list[str]) -> list[str]:
    start = next(
        (index for index, line in enumerate(lines) if line.strip().lower() == _UNRESOLVED_HEADING),
        None,
    )
    if start is None:
        return ["missing '## Unresolved findings' section"]
    unresolved: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if line.strip() and line.strip().lower() not in {"none", "- none"}:
            unresolved.append(line.strip())
    return ["unresolved findings must be empty before an overall PASS"] if unresolved else []


def validate_report(
    path: Path, expected_revision: str | None = None, *, repository: str | None = None
) -> list[str]:
    """Return validation errors for a review evidence report.

    With ``repository`` (``owner/name``), every https screenshot must be hosted by
    GitHub for that repository and must load as an image. CI sets it, because a link
    that 404s still matches the Markdown pattern.
    """
    if not path.is_file():
        return [f"evidence report does not exist: {path}"]
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    errors = []
    if not text.lstrip().startswith("# Review evidence"):
        errors.append("report must start with '# Review evidence'")
    fields = {label: _field(lines, label) for label in _REQUIRED_FIELDS}
    errors.extend(_validate_fields(fields, expected_revision))
    errors.extend(_validate_visual_fields(fields, lines, repository=repository))
    errors.extend(_validate_unresolved(lines))
    ledger_errors, statuses = _ledger_rows(lines)
    errors.extend(ledger_errors)
    if any(status in {"FAIL", "BLOCKED"} for status in statuses):
        errors.append("mandatory ledger criteria cannot be FAIL or BLOCKED before opening a PR")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--revision", help="require the report to name this commit")
    parser.add_argument("--pr-body", type=Path, help="also validate a PR body file")
    parser.add_argument(
        "--check-urls",
        metavar="OWNER/REPO",
        help="require every https screenshot to be this repository's image and to load",
    )
    args = parser.parse_args()
    errors = validate_report(args.report, args.revision, repository=args.check_urls)
    if args.pr_body:
        errors.extend(validate_pr_body(args.pr_body.read_text(encoding="utf-8")))
    if errors:
        print("review evidence invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"review evidence valid: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
