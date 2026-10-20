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


def _pr(state: str = "OPEN", merge: str = "CLEAN", queue: bool = False, armed: bool = False):
    return {
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


if __name__ == "__main__":
    unittest.main()
