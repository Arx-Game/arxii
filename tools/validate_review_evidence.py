"""Validate committed review evidence required before opening a pull request."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

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
_UNRESOLVED_HEADING = "## unresolved findings"


def _field(lines: list[str], label: str) -> str:
    prefix = f"- {label}:"
    for line in lines:
        if line.strip().startswith(prefix):
            return line.strip()[len(prefix) :].strip()
    return ""


def _usable(value: str) -> bool:
    return bool(value) and not _PLACEHOLDER.search(value)


def validate_pr_body(body: str, expected_issue: str | None = None) -> list[str]:
    """Return errors when a PR body omits the durable evidence contract."""
    errors: list[str] = []
    link = re.search(r"^(Refs|Closes) #([0-9]+)$", body, re.MULTILINE)
    if link is None:
        errors.append("PR body must begin with Refs or Closes followed by an issue number")
    elif expected_issue and link.group(2) != expected_issue:
        errors.append(f"PR body links issue #{link.group(2)}, expected #{expected_issue}")
    report = re.search(r"^- Report: `([^`]+)`$", body, re.MULTILINE)
    if report is None:
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


def _validate_screenshot_refs(screenshots: str) -> list[str]:
    errors: list[str] = []
    image_refs = re.findall(r"!\[[^]]*\]\(([^)]+)\)", screenshots)
    if not image_refs:
        return ["screenshots must include at least one Markdown image"]
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


def _validate_visual_fields(fields: dict[str, str], lines: list[str]) -> list[str]:
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
    errors.extend(_validate_screenshot_refs(screenshots))
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


def validate_report(path: Path, expected_revision: str | None = None) -> list[str]:
    """Return validation errors for a review evidence report."""
    if not path.is_file():
        return [f"evidence report does not exist: {path}"]
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    errors = []
    if not text.lstrip().startswith("# Review evidence"):
        errors.append("report must start with '# Review evidence'")
    fields = {label: _field(lines, label) for label in _REQUIRED_FIELDS}
    errors.extend(_validate_fields(fields, expected_revision))
    errors.extend(_validate_visual_fields(fields, lines))
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
    args = parser.parse_args()
    errors = validate_report(args.report, args.revision)
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
