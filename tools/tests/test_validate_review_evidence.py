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

    def test_pr_body_accepts_issue_comment_report_url(self) -> None:
        body = "Refs #3750\n\n## Review evidence\n\n"
        body += "- Report: https://github.com/Arx-Game/arxii/issues/3750#issuecomment-1\n"
        self.assertEqual(validate_pr_body(body, expected_issue="3750"), [])

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


if __name__ == "__main__":
    unittest.main()
