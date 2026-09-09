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
- Application/build identity: local production build
- Environment: Ubuntu, Chromium, fixture backend
- Viewports/themes: desktop 1440px, dark theme
- Visual review: Not applicable (process-only change)
- Screenshots: Not applicable (process-only change)
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
        self.assertIn("does not match HEAD", result.stderr)


if __name__ == "__main__":
    unittest.main()
