"""watch-merge.sh wakes the session when an enqueued PR merges or needs attention (#4521)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "tools/skills/issue-to-merged-pr/scripts/watch-merge.sh"

# Each graphql call answers with the next line of polls.jsonl; no network.
_GH_STUB = """#!/usr/bin/env bash
case "$*" in
  "repo view"*) echo "Arx-Game/arxii" ;;
  "api graphql"*)
    n=$(cat "$STUB_DIR/count" 2>/dev/null || echo 0)
    n=$((n + 1)); echo "$n" > "$STUB_DIR/count"
    line=$(sed -n "${n}p" "$STUB_DIR/polls.jsonl")
    [[ "$line" == FAIL ]] && exit 1
    echo "$line" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
"""


def _pr(  # noqa: PLR0913 - one switch per piece of PR state the watcher reads
    state: str = "OPEN",
    merge: str = "CLEAN",
    queue: bool = False,
    armed: bool = False,
    threads: list[bool] | None = None,
    comments: list[str] | None = None,
):
    pr = {
        "data": {
            "repository": {
                "pullRequest": {
                    "state": state,
                    "mergeStateStatus": merge,
                    "reviewDecision": "APPROVED",
                    "autoMergeRequest": {"enabledAt": "x"} if armed else None,
                    "mergeQueueEntry": (
                        {"state": "AWAITING_CHECKS", "position": 2} if queue else None
                    ),
                }
            }
        }
    }
    node = pr["data"]["repository"]["pullRequest"]
    if threads is not None:
        node["reviewThreads"] = {"nodes": [{"isResolved": done} for done in threads]}
    if comments is not None:
        node["comments"] = {"nodes": [{"body": body} for body in comments]}
    return pr


_CHALLENGE = (
    "<!-- evidence-challenge round=1 verdict=open -->\nShow it.\n"
    "To answer, post a PR comment that starts with `<!-- evidence-answer -->`."
)
_ANSWER = "<!-- evidence-answer -->\nHere it is."
_RESOLVED = "<!-- evidence-challenge round=2 verdict=satisfied -->\nThanks."


def _run(polls: list, cap: int = 3600) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        bindir = Path(tmp, "bin")
        bindir.mkdir()
        gh = bindir / "gh"
        gh.write_text(_GH_STUB)
        gh.chmod(0o755)
        Path(tmp, "polls.jsonl").write_text(
            "\n".join(p if isinstance(p, str) else json.dumps(p) for p in polls) + "\n"
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(
            PATH=f"{bindir}:{env['PATH']}",
            STUB_DIR=tmp,
            WATCH_MERGE_INTERVAL="0",
            WATCH_MERGE_CAP=str(cap),
        )
        return subprocess.run(
            ["bash", str(WATCH), "5"], env=env, capture_output=True, text=True, check=False
        )


class WatchMergeTests(unittest.TestCase):
    def test_queued_then_merged_exits_zero(self) -> None:
        result = _run([_pr(queue=True), _pr(armed=True), _pr(state="MERGED")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MERGED #5", result.stdout)

    def test_one_unarmed_poll_before_the_merge_is_not_a_drop(self) -> None:
        result = _run([_pr(queue=True), _pr(), _pr(state="MERGED")])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_two_unarmed_polls_in_a_row_is_a_drop(self) -> None:
        result = _run([_pr(queue=True), _pr(), _pr()])
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("DROPPED", result.stdout)

    def test_conflicting_wakes_at_once(self) -> None:
        result = _run([_pr(armed=True), _pr(merge="DIRTY", armed=True)])
        self.assertEqual(result.returncode, 8, result.stderr)

    def test_closed_without_merging(self) -> None:
        result = _run([_pr(state="CLOSED")])
        self.assertEqual(result.returncode, 7, result.stderr)

    def test_a_transient_gh_failure_keeps_waiting(self) -> None:
        result = _run([_pr(queue=True), "FAIL", _pr(state="MERGED")])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_three_gh_failures_in_a_row_give_up(self) -> None:
        result = _run(["FAIL", "FAIL", "FAIL"])
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_still_waiting_at_the_cap_times_out(self) -> None:
        result = _run([_pr(queue=True)], cap=0)
        self.assertEqual(result.returncode, 6, result.stderr)

    def test_an_unresolved_review_thread_needs_an_answer(self) -> None:
        result = _run([_pr(armed=True, threads=[True, False])])
        self.assertEqual(result.returncode, 10, result.stderr)
        self.assertIn("NEEDS_ANSWER #5: 1 unresolved review thread", result.stdout)

    def test_an_open_evidence_challenge_needs_an_answer(self) -> None:
        result = _run([_pr(queue=True, comments=[_CHALLENGE])])
        self.assertEqual(result.returncode, 10, result.stderr)
        self.assertIn("evidence challenge open", result.stdout)

    def test_an_answered_challenge_keeps_waiting(self) -> None:
        result = _run([_pr(armed=True, threads=[True], comments=[_CHALLENGE, _ANSWER])], cap=0)
        self.assertEqual(result.returncode, 6, result.stderr)

    def test_a_new_round_after_the_answer_needs_an_answer(self) -> None:
        result = _run([_pr(armed=True, comments=[_CHALLENGE, _ANSWER, _CHALLENGE])])
        self.assertEqual(result.returncode, 10, result.stderr)

    def test_a_challenge_quoting_the_answer_marker_is_still_open(self) -> None:
        # The challenger's own instructions quote the answer marker mid-comment.
        result = _run([_pr(armed=True, comments=[_CHALLENGE])])
        self.assertEqual(result.returncode, 10, result.stderr)

    def test_a_newer_satisfied_round_clears_an_older_open_one(self) -> None:
        result = _run([_pr(armed=True, comments=[_CHALLENGE, _RESOLVED])], cap=0)
        self.assertEqual(result.returncode, 6, result.stderr)

    def test_a_resolved_challenge_keeps_waiting(self) -> None:
        result = _run([_pr(armed=True, comments=[_CHALLENGE, _ANSWER, _RESOLVED])], cap=0)
        self.assertEqual(result.returncode, 6, result.stderr)


if __name__ == "__main__":
    unittest.main()
