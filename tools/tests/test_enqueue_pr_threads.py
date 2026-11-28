"""enqueue-pr.sh must refuse while any review thread is unresolved (#4510), and while
SonarCloud holds an open issue on the PR's head or has not analyzed it yet (#4850). It
must also tell a code-scanning alert from a token that cannot read alerts (#5329)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENQUEUE = ROOT / "tools/skills/issue-to-merged-pr/scripts/enqueue-pr.sh"

# Every gh call enqueue-pr.sh makes before the thread check; no network. The two
# security reads answer from fixture files and apply the caller's --jq filter with
# jq, as gh does, so the script's own filters are what the tests run. A fixture
# named "forbidden" answers the way gh api does on an HTTP error: the response body
# on stdout, then a non-zero exit.
_GH_STUB = """#!/usr/bin/env bash
ARGS=("$@")
forbidden() {
  echo '{"message":"Resource not accessible by personal access token","status":"403"}'
  echo "gh: Resource not accessible by personal access token (HTTP 403)" >&2
  exit 1
}
answer() {
  [[ "$1" == "forbidden" ]] && forbidden
  local filter="" prev=""
  for arg in "${ARGS[@]}"; do
    [[ "$prev" == "--jq" ]] && filter="$arg"
    prev="$arg"
  done
  jq -r "$filter" "$1"
}
case "$*" in
  "repo view"*) echo "Arx-Game/arxii" ;;
  "pr view"*headRefName*) echo "feature-1" ;;
  "pr view"*body*) echo "Closes #7" ;;
  "issue view"*) echo '{"labels":[],"body":""}' ;;
  "api repos/"*"/code-scanning/alerts"*) answer "$STUB_ALERTS" ;;
  "api graphql"*) answer "$STUB_BOT_THREADS" ;;
  "api repos/"*) echo "" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
"""

FORBIDDEN = "forbidden"


def _alert(state: str | None, path: str) -> dict:
    """One code-scanning alert as the REST API lists it for a PR ref."""
    return {
        "state": state,
        "rule": {"id": "py/stack-trace-exposure", "security_severity_level": "medium"},
        "most_recent_instance": {"location": {"path": path, "start_line": 40}},
    }


def _bot_thread(login: str | None, path: str, *, resolved: bool = False) -> dict:
    """One review thread as the fallback's GraphQL query returns it."""
    author = None if login is None else {"login": login}
    return {
        "isResolved": resolved,
        "isOutdated": False,
        "path": path,
        "line": 40,
        "comments": {"nodes": [{"author": author, "body": "Information exposure\nmore"}]},
    }


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
    threads: list[dict],
    sonar: tuple[dict, dict] | None = None,
    *,
    alerts: list[dict] | str = (),
    bot_threads: list[dict] | str = (),
) -> subprocess.CompletedProcess[str]:
    """Run the dry run. ``alerts`` and ``bot_threads`` are what the code-scanning
    API and the fallback's review-thread query answer; ``FORBIDDEN`` makes that
    call fail the way gh does on an HTTP error."""
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
        if alerts == FORBIDDEN:
            env["STUB_ALERTS"] = FORBIDDEN
        else:
            Path(tmp, "alerts.json").write_text(json.dumps(list(alerts)))
            env["STUB_ALERTS"] = str(Path(tmp, "alerts.json"))
        if bot_threads == FORBIDDEN:
            env["STUB_BOT_THREADS"] = FORBIDDEN
        else:
            nodes = {"reviewThreads": {"nodes": list(bot_threads)}}
            Path(tmp, "bot_threads.json").write_text(
                json.dumps({"data": {"repository": {"pullRequest": nodes}}})
            )
            env["STUB_BOT_THREADS"] = str(Path(tmp, "bot_threads.json"))
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


class EnqueueSecurityFindingGateTests(unittest.TestCase):
    """The token agents use gets HTTP 403 from the code-scanning API. That is not a
    finding: the script then reads the security bot's review threads instead."""

    BOT = "github-advanced-security"

    def test_an_open_alert_refuses_and_lists_it(self) -> None:
        alerts = [_alert("open", "src/web/views.py"), _alert("fixed", "src/web/old.py")]
        result = _run([], alerts=alerts)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("unresolved GitHub Advanced Security findings", result.stderr)
        self.assertIn("[medium] py/stack-trace-exposure at src/web/views.py:40", result.stderr)
        self.assertNotIn("src/web/old.py", result.stderr)

    def test_unreadable_alerts_with_no_bot_thread_pass_and_say_what_was_checked(self) -> None:
        human = _bot_thread("ApostateCD", "src/web/human.py")
        result = _run([], alerts=FORBIDDEN, bot_threads=[human])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[dry-run]", result.stdout)
        self.assertIn("cannot read code-scanning alerts", result.stderr)
        self.assertNotIn("Resource not accessible", result.stderr)
        self.assertNotIn("unresolved GitHub Advanced Security findings", result.stderr)

    def test_unreadable_alerts_with_an_open_bot_thread_refuse_and_list_it(self) -> None:
        threads = [
            _bot_thread(self.BOT, "src/web/views.py"),
            _bot_thread(self.BOT, "src/web/done.py", resolved=True),
            _bot_thread(None, "src/web/ghost.py"),
        ]
        result = _run([], alerts=FORBIDDEN, bot_threads=threads)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("unresolved GitHub Advanced Security findings", result.stderr)
        self.assertIn("src/web/views.py:40  Information exposure", result.stderr)
        self.assertNotIn("src/web/done.py", result.stderr)
        self.assertNotIn("src/web/ghost.py", result.stderr)
        self.assertNotIn("Resource not accessible", result.stderr)

    def test_unreadable_alerts_and_unreadable_threads_refuse(self) -> None:
        result = _run([], alerts=FORBIDDEN, bot_threads=FORBIDDEN)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("could not read", result.stderr)
        self.assertNotIn("[dry-run]", result.stdout)
        self.assertNotIn("unresolved GitHub Advanced Security findings", result.stderr)


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
