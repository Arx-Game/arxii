"""Tests for the fail-closed issue phase transition helper."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/skills/issue-to-merged-pr/scripts/transition-issue-phase.sh"

BODY = """## Discovery assessment

- Outcome: bounded workflow change.
- Success signal: the transition is verified.
- Stakeholder provenance: maintainer / workflow agents / implementer / maintainer.
- Impact: tooling-only and reversible.
- Lane rationale: explicit bounded change.
<!-- discovery:lane=lightweight;state=complete -->

<!-- spec:start -->
Spec.
<!-- spec:end -->
"""

GH_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
STATE_FILE="${TRANSITION_STATE_FILE:?}"
MODE="${TRANSITION_MODE:-success}"
case "$*" in
  "api user"*) echo "test-user"; exit 0 ;;
  *"issue view"*) cat "$STATE_FILE"; exit 0 ;;
  *"issue edit"*)
    if [[ "$MODE" == "edit-failure" ]]; then
      echo "simulated GitHub failure" >&2
      exit 1
    fi
    if [[ "$MODE" == "body-conflict" ]]; then
      tmp=$(mktemp)
      jq '.body += "\nconcurrent edit"' "$STATE_FILE" > "$tmp"
      mv "$tmp" "$STATE_FILE"
    elif [[ "$MODE" == "claim-conflict" ]]; then
      tmp=$(mktemp)
      jq '.assignees = [{"login":"other-user"}]' "$STATE_FILE" > "$tmp"
      mv "$tmp" "$STATE_FILE"
    fi
    remove=""
    add=""
    while (($#)); do
      case "$1" in
        --remove-label) remove="$2"; shift 2 ;;
        --add-label) add="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    tmp=$(mktemp)
    jq --arg remove "$remove" --arg add "$add" \
      '.labels = ([.labels[] | select(.name != $remove)] + [{"name":$add}])' \
      "$STATE_FILE" > "$tmp"
    mv "$tmp" "$STATE_FILE"
    exit 0
    ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
"""


class TransitionIssuePhaseTests(unittest.TestCase):
    def run_helper(self, mode: str = "success") -> tuple[subprocess.CompletedProcess[str], dict]:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            state_path = directory_path / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "state": "OPEN",
                        "body": BODY,
                        "labels": [{"name": "status:spec-draft"}],
                        "assignees": [{"login": "test-user"}],
                    }
                )
            )
            gh = directory_path / "gh"
            gh.write_text(GH_STUB)
            gh.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{directory}{os.pathsep}{env['PATH']}"
            env["TRANSITION_STATE_FILE"] = str(state_path)
            env["TRANSITION_MODE"] = mode
            result = subprocess.run(
                [str(SCRIPT), "3958", "status:spec-draft", "status:implementing"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            return result, json.loads(state_path.read_text())

    def test_success_reports_verified_transition(self) -> None:
        result, state = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("transition: status:spec-draft -> status:implementing", result.stdout)
        self.assertEqual([label["name"] for label in state["labels"]], ["status:implementing"])

    def test_body_change_fails_closed(self) -> None:
        result, state = self.run_helper("body-conflict")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("issue body changed", result.stderr)
        self.assertIn("Recovery:", result.stderr)
        self.assertEqual([label["name"] for label in state["labels"]], ["status:implementing"])

    def test_claim_change_fails_closed(self) -> None:
        result, _ = self.run_helper("claim-conflict")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("assignee or claim changed", result.stderr)

    def test_github_edit_failure_reports_recovery(self) -> None:
        result, state = self.run_helper("edit-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GitHub rejected", result.stderr)
        self.assertIn("inspect the labels", result.stderr)
        self.assertEqual([label["name"] for label in state["labels"]], ["status:spec-draft"])


if __name__ == "__main__":
    unittest.main()
