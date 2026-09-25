"""Tests for the issue discovery state validator."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "skills" / "issue-to-merged-pr" / "scripts" / "validate-discovery.sh"


LIGHTWEIGHT = """Issue.

## Discovery assessment

- Outcome: bounded change.
- Success signal: the check passes.
- Stakeholder provenance: reporter / affected user / implementer / decision-maker.
- Impact: low and reversible.
- Lane rationale: existing pattern with no outcome fork.
<!-- discovery:lane=lightweight;state=complete -->

<!-- spec:start -->
### Goal
Example.
<!-- spec:end -->
"""


STANDARD = """Issue.

## Discovery assessment

- Outcome: users choose a direction.
- Success signal: stakeholder selects one.
- Stakeholder provenance: reporter / affected user / implementer / decision-maker.
- Impact: player-facing and reversible.
- Lane rationale: multiple outcome forks.
- Users: players and staff.
- Non-goals: unrelated redesign.
- Outcome-changing assumptions: the audience needs two paths.
- Options: A or B with consequences.
- Scenarios: owner, stranger, and staff state transitions.
<!-- discovery:lane=standard;state=awaiting-stakeholder -->

<!-- spec:start -->
### Goal
Example.
<!-- spec:end -->
"""


class DiscoveryValidatorTests(unittest.TestCase):
    def run_validator(self, body: str, labels: str) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile("w", suffix=".md") as handle:
            handle.write(body)
            handle.flush()
            return subprocess.run(
                [str(SCRIPT), "3956", "--body-file", handle.name, "--labels", labels],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_complete_lightweight_lane_can_implement_without_approval(self) -> None:
        result = self.run_validator(LIGHTWEIGHT, "status:implementing")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_approved_legacy_issue_can_open_until_marker_migration(self) -> None:
        body = "Issue without a discovery marker.\n<!-- spec:start -->\nSpec.\n<!-- spec:end -->\n"
        with tempfile.NamedTemporaryFile("w", suffix=".md") as handle:
            handle.write(body)
            handle.flush()
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "3933",
                    "--body-file",
                    handle.name,
                    "--labels",
                    "status:implementing,spec:approved",
                    "--allow-approved-legacy",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("legacy-approved", result.stdout)

    def test_unlisted_approved_legacy_issue_is_rejected(self) -> None:
        body = "Issue without a discovery marker.\n<!-- spec:start -->\nSpec.\n<!-- spec:end -->\n"
        with tempfile.NamedTemporaryFile("w", suffix=".md") as handle:
            handle.write(body)
            handle.flush()
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "3956",
                    "--body-file",
                    handle.name,
                    "--labels",
                    "status:implementing,spec:approved",
                    "--allow-approved-legacy",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not in the temporary legacy compatibility allowlist", result.stderr)

    def test_standard_lane_can_wait_for_stakeholder(self) -> None:
        result = self.run_validator(STANDARD, "status:spec-draft")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_standard_lane_cannot_bypass_approval(self) -> None:
        result = self.run_validator(STANDARD, "status:implementing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires a complete lightweight marker", result.stderr)

    def test_completed_standard_packet_can_enter_spec_review(self) -> None:
        body = STANDARD.replace("state=awaiting-stakeholder", "state=complete")
        result = self.run_validator(body, "status:spec-review")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_marker_inside_spec_does_not_count(self) -> None:
        body = """Issue.

<!-- spec:start -->
<!-- discovery:lane=lightweight;state=complete -->
<!-- spec:end -->
"""
        result = self.run_validator(body, "status:implementing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one state marker", result.stderr)

    def test_standard_lane_does_not_duplicate_the_prd_packet(self) -> None:
        body = STANDARD.replace("- Scenarios: owner, stranger, and staff state transitions.\n", "")
        result = self.run_validator(body, "status:spec-draft")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_assessment_rejects_empty_field_values(self) -> None:
        body = LIGHTWEIGHT.replace("- Outcome: bounded change.", "- Outcome:")
        result = self.run_validator(body, "status:implementing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Outcome", result.stderr)


if __name__ == "__main__":
    unittest.main()
