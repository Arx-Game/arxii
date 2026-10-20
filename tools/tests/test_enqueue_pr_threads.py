"""enqueue-pr.sh must refuse while any review thread is unresolved (#4510)."""

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


def _run(threads: list[dict]) -> subprocess.CompletedProcess[str]:
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
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env["PATH"] = f"{bindir}:{env['PATH']}"
        env["ENQUEUE_THREADS_JSON_FILE"] = str(data)
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


if __name__ == "__main__":
    unittest.main()
