"""Regression tests for the pre-PR review evidence contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

_VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "validate_review_evidence", Path(__file__).resolve().parents[1] / "validate_review_evidence.py"
)
if _VALIDATOR_SPEC is None or _VALIDATOR_SPEC.loader is None:
    raise SystemExit
_VALIDATOR = importlib.util.module_from_spec(_VALIDATOR_SPEC)
_VALIDATOR_SPEC.loader.exec_module(_VALIDATOR)
validate_pr_body = _VALIDATOR.validate_pr_body

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "validate_review_evidence.py"


class ReviewEvidenceTests(unittest.TestCase):
    def test_archived_3735_pr_body_is_rejected(self) -> None:
        body = (ROOT / "tools/tests/fixtures/pr-3735-body.md").read_text()
        errors = validate_pr_body(body, expected_issue="3731")
        self.assertIn("missing the committed review report link", " ".join(errors))

    def test_pr_body_accepts_terminal_punctuation_after_issue_reference(self) -> None:
        body = "Closes #3748.\n\n## Review evidence\n\n"
        body += "- Report: `docs/reviews/3748.md`\n"
        self.assertEqual(validate_pr_body(body, expected_issue="3748"), [])

    def test_unlinked_pr_has_no_opt_in_issue(self) -> None:
        self.assertIsNone(_VALIDATOR.linked_issue_number("Dependabot update\n"))

    def test_linked_issue_number_ignores_unrelated_issue_mentions(self) -> None:
        body = "See #3748 for context.\n\nRefs #3750.\n"
        self.assertEqual(_VALIDATOR.linked_issue_number(body), "3750")

    def test_pr_body_accepts_issue_comment_report_url(self) -> None:
        body = "Closes #3750\n\n## Review evidence\n\n"
        body += "- Report: https://github.com/Arx-Game/arxii/issues/3750#issuecomment-1\n"
        self.assertEqual(validate_pr_body(body, expected_issue="3750"), [])

    def test_pr_body_rejects_reference_without_closing_issue(self) -> None:
        body = "Refs #3750\n\n## Review evidence\n\n"
        body += "- Report: https://github.com/Arx-Game/arxii/issues/3750#issuecomment-1\n"
        errors = validate_pr_body(body, expected_issue="3750")
        self.assertIn("must include a line of the form Closes", " ".join(errors))

    def test_closing_issue_number_ignores_reference_only(self) -> None:
        self.assertIsNone(_VALIDATOR.closing_issue_number("Refs #3750\n"))
        self.assertEqual(_VALIDATOR.closing_issue_number("Closes #3750\n"), "3750")

    def test_closing_issue_number_found_anywhere_in_the_body(self) -> None:
        """#3938: the line need not be the first thing in the body."""
        body = "Summary\n\nCloses #3750\n"
        self.assertEqual(_VALIDATOR.closing_issue_number(body), "3750")

    def test_closing_issue_number_ignores_mid_line_occurrence(self) -> None:
        """It must still be its own line, not merely present somewhere in one."""
        body = "See Closes #3750 in the summary above.\n"
        self.assertIsNone(_VALIDATOR.closing_issue_number(body))

    def test_dependabot_accounts_are_exempt_from_closing_issue_requirement(self) -> None:
        self.assertTrue(_VALIDATOR.is_dependabot_login("dependabot[bot]"))
        self.assertTrue(_VALIDATOR.is_dependabot_login("dependabot-preview[bot]"))
        self.assertFalse(_VALIDATOR.is_dependabot_login("release-bot[bot]"))
        self.assertFalse(_VALIDATOR.is_dependabot_login(None))

    def test_archived_3735_shape_is_rejected(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(ROOT / "tools/tests/fixtures/pr-3735-body.md")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("report must start", result.stderr)

    def test_complete_report_is_bound_to_exact_revision(self) -> None:
        revision = "a" * 40
        report = f"""# Review evidence

- Reviewed revision: `{revision}`
- Reviewer: local reviewer agent
- Reviewer verdict: PASS
- Application/build identity: local production build
- Environment: Ubuntu, Chromium, fixture backend
- Viewports/themes: desktop 1440px, dark theme
- Approved design: Not applicable (process-only change)
- Visual review: Not applicable (process-only change)
- Visual verdict: NOT_APPLICABLE
- Screenshots: Not applicable (process-only change)
- Comparison notes: Not applicable (process-only change)
- Tested interactions: validator rejection and acceptance paths
- Fixture/live boundary: validator-only; no live player data
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 | PASS | test_validate_review_evidence.py | |
| A02 | OUT_OF_SCOPE | | Authorized: process-only change |

## Unresolved findings

- None
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.md"
            path.write_text(report, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), "--revision", revision],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unresolved_finding_is_rejected(self) -> None:
        revision = "d" * 40
        report = (ROOT / "tools/tests/fixtures/stale-review-evidence.md").read_text()
        report = report.replace("REVISION", revision).replace("- None", "- A01 remains unresolved")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.md"
            path.write_text(report, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), "--revision", revision],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved findings", result.stderr)

    def test_visual_review_requires_a_real_image(self) -> None:
        revision = "e" * 40
        report = (ROOT / "tools/tests/fixtures/stale-review-evidence.md").read_text()
        report = report.replace("REVISION", revision).replace(
            "- Reviewer: fixture reviewer", "- Reviewer: local reviewer agent"
        )
        report = report.replace("Not applicable (process-only fixture)", "design URL")
        report = report.replace(
            "- Visual review: Not applicable (process-only change)",
            "- Visual review: Completed",
        )
        report = report.replace("- Visual verdict: NOT_APPLICABLE", "- Visual verdict: PASS")
        report = report.replace(
            "- Screenshots: Not applicable (process-only change)",
            "- Screenshots: ![ready](shot.png)",
        )
        report = report.replace(
            "- Comparison notes: Not applicable (process-only fixture)",
            "- Comparison notes: Compared ready state with approved design",
        )
        report = report.replace(
            "## Requirement ledger",
            "## Visual checklist\n\n"
            "| Element | Expected | Result | Evidence |\n"
            "|---|---|---|---|\n"
            "| Ready state | reader and composer visible | MATCH | ![ready](shot.png) |\n\n"
            "## Requirement ledger",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.md"
            path.write_text(report, encoding="utf-8")
            (Path(directory) / "shot.png").write_bytes(b"PNG fixture")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), "--revision", revision],
                capture_output=True,
                text=True,
                cwd=directory,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            mismatch_path = Path(directory) / "mismatch.md"
            mismatch_path.write_text(report.replace("| MATCH |", "| MISMATCH |"), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(mismatch_path), "--revision", revision],
                capture_output=True,
                text=True,
                cwd=directory,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not marked MATCH", result.stderr)
            (Path(directory) / "shot.png").unlink()
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), "--revision", revision],
                capture_output=True,
                text=True,
                cwd=directory,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("screenshot file does not exist", result.stderr)

    def test_stale_revision_is_rejected(self) -> None:
        revision = "b" * 40
        report = (ROOT / "tools/tests/fixtures/stale-review-evidence.md").read_text()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.md"
            path.write_text(report.replace("REVISION", "c" * 40), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), "--revision", revision],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the reviewed code revision", result.stderr)


REPO = "Arx-Game/arxii"
SCREEN = ["frontend/src/roster/CharacterSheet.tsx", "src/world/roster/views.py"]
SONAR_BADGE = (
    "![Quality Gate passed](https://sonarcloud.io/api/project_badges/quality_gate?project=arxii)"
)


class FrontendScreenshotTests(unittest.TestCase):
    """Regression for #5310: a PR that changed screen code reached main with no picture."""

    def test_screen_change_without_a_screenshot_is_refused(self) -> None:
        """Regression for #5310. A bot's badge image is not a screenshot of the change."""
        errors = _VALIDATOR.frontend_screenshot_errors(f"Closes #1\n{SONAR_BADGE}\n", SCREEN, REPO)
        self.assertEqual(len(errors), 1)
        self.assertIn("just shot-post", errors[0])

    def test_stated_reason_or_test_only_change_needs_no_screenshot(self) -> None:
        """Regression for #5310. Test files and a stated reason are not screen changes."""
        body = "Closes #1\nNo visual change: renames a prop; the page renders the same.\n"
        self.assertEqual(_VALIDATOR.frontend_screenshot_errors(body, SCREEN, REPO), [])
        tests_only = ["frontend/src/roster/__tests__/Sheet.test.tsx", "frontend/src/test/x.tsx"]
        self.assertEqual(_VALIDATOR.frontend_screenshot_errors("Closes #1\n", tests_only, REPO), [])

    def test_placeholder_reason_does_not_count(self) -> None:
        """Regression for #5310. `No visual change: <reason>` copied verbatim is no reason."""
        body = "Closes #1\nNo visual change: <reason>\n"
        self.assertEqual(len(_VALIDATOR.frontend_screenshot_errors(body, SCREEN, REPO)), 1)

    def test_only_images_this_repository_hosts_count(self) -> None:
        """Regression for #5310. Raw links into another repository are not this PR's evidence."""
        own = f"![sheet](https://raw.githubusercontent.com/{REPO}/{'a' * 40}/01-sheet.png)"
        other = f"![x](https://raw.githubusercontent.com/someone/else/{'a' * 40}/x.png)"
        attached = '<img src="https://github.com/user-attachments/assets/abc" width="400">'
        found = _VALIDATOR.hosted_image_urls(f"{own}\n{other}\n{attached}\n{SONAR_BADGE}", REPO)
        self.assertEqual(
            found,
            [
                f"https://raw.githubusercontent.com/{REPO}/{'a' * 40}/01-sheet.png",
                "https://github.com/user-attachments/assets/abc",
            ],
        )


class NoIssueTests(unittest.TestCase):
    def test_chore_pr_states_why_it_closes_no_issue(self) -> None:
        """Regression for #5310. Chore and dependency PRs failed the closes-an-issue rule."""
        body = "Bumps four dev dependencies.\n\nNo issue: routine dependency update.\n"
        self.assertEqual(_VALIDATOR.no_issue_reason(body), "routine dependency update.")
        self.assertIsNone(_VALIDATOR.no_issue_reason("Bumps things.\nNo issue: TBD\n"))
        self.assertIsNone(_VALIDATOR.no_issue_reason("Bumps things, no issue: none.\n"))


if __name__ == "__main__":
    unittest.main()
