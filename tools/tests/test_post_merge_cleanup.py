"""post-merge-cleanup.sh must finish cleanly when run from the worktree it removes.

The script removed the branch worktree and then ran ``gh pr view`` from that
deleted directory, which fails with "Unable to read current working directory"
and turned a successful cleanup into a nonzero exit (#3978).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLEANUP = ROOT / "tools/skills/issue-to-merged-pr/scripts/post-merge-cleanup.sh"
BRANCH = "feature-3978"
PR = "42"

# Real gh runs git in its cwd; the stub fails the same way when that cwd is gone.
_GH_STUB = """#!/usr/bin/env bash
if [[ ! -d "$PWD" ]]; then
  echo "fatal: Unable to read current working directory: No such file or directory" >&2
  exit 128
fi
case "$*" in
  "pr view"*body*) echo "Closes #7" ;;
  "pr view"*state*) echo "MERGED" ;;
  "issue view 7"*) echo "CLOSED" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
"""


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@unittest.skipIf(os.name == "nt", "Windows refuses to delete a process's cwd; CI runs Linux")
class PostMergeCleanupTests(unittest.TestCase):
    def test_run_from_branch_worktree_verifies_pr_after_removing_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            origin = base / "origin.git"
            main = base / "main"
            branch_wt = base / "branch-wt"
            bin_dir = base / "bin"
            bin_dir.mkdir()
            gh = bin_dir / "gh"
            gh.write_text(_GH_STUB, encoding="utf-8")
            gh.chmod(0o755)

            _git("init", "--bare", "-b", "main", str(origin), cwd=base)
            _git("clone", str(origin), str(main), cwd=base)
            _git(
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "commit",
                "--allow-empty",
                "-m",
                "init",
                cwd=main,
            )
            _git("push", "origin", "main", cwd=main)
            _git("worktree", "add", "-b", BRANCH, str(branch_wt), cwd=main)

            env = dict(os.environ)
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
            result = subprocess.run(
                ["bash", str(CLEANUP), BRANCH, PR],
                cwd=branch_wt,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(branch_wt.exists())
            # `git branch -d` prints "Deleted branch ..." ahead of the JSON summary.
            summary = json.loads(result.stdout[result.stdout.index("{") :])
            self.assertEqual(summary["branch_deleted"], BRANCH)
            self.assertEqual(
                summary["linked_issue_actions"],
                [{"issue": 7, "state": "CLOSED", "action": "auto-closed"}],
            )
