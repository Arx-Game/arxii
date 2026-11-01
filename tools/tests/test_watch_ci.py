"""watch-ci.sh does not call a PR "OK" while review threads wait (#4882).

Green checks used to print OK even with the code-review bot's blocking comments
unread; the ruleset requires every thread resolved, so that was a false all-clear.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "tools/skills/issue-to-merged-pr/scripts/watch-ci.sh"

_GH_STUB = """#!/usr/bin/env bash
case "$*" in
  "pr view"*"statusCheckRollup"*) cat "$STUB_DIR/rollup.json" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
"""

GREEN = [
    {"name": n, "status": "COMPLETED", "conclusion": "SUCCESS"}
    for n in ("backend", "frontend", "review")
]


def _threads(*resolved: bool) -> dict:
    nodes = [
        {
            "id": f"T{i}",
            "isResolved": done,
            "path": "tools/x.sh",
            "line": 54,
            "comments": {
                "nodes": [{"author": {"login": "github-actions"}, "body": f"finding {i}\nmore"}]
            },
        }
        for i, done in enumerate(resolved)
    ]
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}}


def _watch(tmp_path: Path, rollup: list, threads: dict) -> subprocess.CompletedProcess:
    (tmp_path / "gh").write_text(_GH_STUB)
    (tmp_path / "gh").chmod(0o755)
    (tmp_path / "rollup.json").write_text(json.dumps(rollup))
    (tmp_path / "threads.json").write_text(json.dumps(threads))
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "STUB_DIR": str(tmp_path),
        "WATCH_CI_THREADS_JSON_FILE": str(tmp_path / "threads.json"),
    }
    return subprocess.run(
        ["bash", str(WATCH), "5"], env=env, capture_output=True, text=True, check=False
    )


def test_green_checks_with_no_open_thread_are_ok(tmp_path: Path):
    proc = _watch(tmp_path, GREEN, _threads(True))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "OK"


def test_green_checks_with_an_open_thread_are_not_ok(tmp_path: Path):
    proc = _watch(tmp_path, GREEN, _threads(True, False, False))

    assert proc.returncode == 11, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0] == "REVIEW 2 unresolved thread(s)"
    assert "tools/x.sh:54 [github-actions] finding 1" in lines[1]
    assert lines[1].endswith("(thread T1)")


@pytest.mark.parametrize("conclusion", ["FAILURE", "CANCELLED"])
def test_a_failing_check_still_wins(tmp_path: Path, conclusion: str):
    rollup = [*GREEN, {"name": "pre-commit", "status": "COMPLETED", "conclusion": conclusion}]
    proc = _watch(tmp_path, rollup, _threads(False))
    assert proc.returncode == 5
    assert proc.stdout.strip() == "FAIL pre-commit"
