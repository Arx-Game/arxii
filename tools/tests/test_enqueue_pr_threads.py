"""enqueue-pr.sh must refuse while any review thread is unresolved (#4510), and while
SonarCloud holds an open issue on the PR's head or has not analyzed it yet (#4850)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENQUEUE = ROOT / "tools/skills/issue-to-merged-pr/scripts/enqueue-pr.sh"

# Every gh call enqueue-pr.sh makes before the thread check; no network.
_GH_STUB = """#!/usr/bin/env bash
case "$*" in
  "repo view"*) echo "Arx-Game/arxii" ;;
  "pr view"*headRefName*) echo "feature-1" ;;
  "pr view"*body*) echo "Closes #7" ;;
  "issue view"*) echo '{"labels":[],"body":""}' ;;
  "api repos/"*) echo "" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
"""


def _thread(tid: str, resolved: bool) -> dict:
    return {
        "id": tid,
        "isResolved": resolved,
        "path": "src/a.py",
        "line": 12,
        "comments": {"nodes": [{"body": "**[logic]** wrong sign\nmore"}]},
    }


def _sonar(analyzed: str | None, issues: int = 0) -> tuple[dict, dict]:
    """SonarCloud's PR list (PR 5 analyzed at ``analyzed``) and its open issues."""
    pulls = [] if analyzed is None else [{"key": "5", "commit": {"sha": analyzed}}]
    found = [
        {
            "rule": "python:S5886",
            "component": "Arx-Game_arxii:src/world/mechanics/types.py",
            "line": 240,
            "message": "Return a value of type X",
        }
    ] * issues
    return {"pullRequests": pulls}, {"issues": found}


def _run(
    threads: list[dict], sonar: tuple[dict, dict] | None = None
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        bindir = Path(tmp, "bin")
        bindir.mkdir()
        gh = bindir / "gh"
        gh.write_text(_GH_STUB)
        gh.chmod(0o755)
        data = Path(tmp, "threads.json")
        data.write_text(
            json.dumps(
                {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": threads}}}}}
            )
        )
        pulls, issues = sonar or _sonar("head5")
        Path(tmp, "pulls.json").write_text(json.dumps(pulls))
        Path(tmp, "issues.json").write_text(json.dumps(issues))
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env["PATH"] = f"{bindir}:{env['PATH']}"
        env["ENQUEUE_THREADS_JSON_FILE"] = str(data)
        env["ENQUEUE_HEAD_SHA"] = "head5"
        env["SONAR_PR_JSON_FILE"] = str(Path(tmp, "pulls.json"))
        env["SONAR_ISSUES_JSON_FILE"] = str(Path(tmp, "issues.json"))
        return subprocess.run(
            ["bash", str(ENQUEUE), "--dry-run", "5"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )


class EnqueueThreadGateTests(unittest.TestCase):
    def test_unresolved_thread_refuses_and_lists_it(self) -> None:
        result = _run([_thread("T_open", False), _thread("T_done", True)])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("src/a.py:12", result.stderr)
        self.assertIn("**[logic]** wrong sign", result.stderr)
        self.assertIn("T_open", result.stderr)
        self.assertNotIn("T_done", result.stderr)
        self.assertIn("resolveReviewThread", result.stderr)

    def test_all_resolved_passes_the_dry_run(self) -> None:
        result = _run([_thread("T_done", True)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[dry-run]", result.stdout)


class EnqueueSonarGateTests(unittest.TestCase):
    def test_an_open_sonarcloud_issue_refuses_and_lists_it(self) -> None:
        result = _run([_thread("T_done", True)], sonar=_sonar("head5", issues=1))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("open SonarCloud issues", result.stderr)
        self.assertIn("python:S5886 src/world/mechanics/types.py:240", result.stderr)
        self.assertNotIn("[dry-run]", result.stdout)

    def test_an_analysis_of_an_older_commit_refuses(self) -> None:
        result = _run([_thread("T_done", True)], sonar=_sonar("old1234567"))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("has not analyzed", result.stderr)

    def test_a_pr_sonarcloud_never_listed_refuses(self) -> None:
        result = _run([_thread("T_done", True)], sonar=_sonar(None))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("newest: none", result.stderr)

    def test_a_clean_analysis_of_the_head_passes(self) -> None:
        result = _run([_thread("T_done", True)], sonar=_sonar("head5"))
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
