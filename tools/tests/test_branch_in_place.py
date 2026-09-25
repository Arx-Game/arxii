"""Branch-in-place mode: on the memory-capped solo machine a branch lives in the main tree.

CLAUDE.md scopes the worktree rule by machine (2026-09-25): under 8 GiB of visible
memory a single sequential agent branches in the main checkout instead of a
worktree. ``_wt-helpers.sh`` carries that decision (``wt_branch_in_place``, with
``ARXII_BRANCH_IN_PLACE`` as the explicit override) so ``start-work.sh`` and
``post-merge-cleanup.sh`` agree on it. Cleanup used to resolve the branch's
worktree and, for a branch checked out in the main tree, ran
``git worktree remove`` against the main working tree itself.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools/skills/issue-to-merged-pr/scripts"
HELPERS = SCRIPTS / "_wt-helpers.sh"
CLEANUP = SCRIPTS / "post-merge-cleanup.sh"
BRANCH = "feature-4010"
PR = "42"

_GH_STUB = """#!/usr/bin/env bash
case "$*" in
  "pr view"*body*) echo "Closes #7" ;;
  "pr view"*state*) echo "MERGED" ;;
  "issue view 7"*) echo "CLOSED" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
"""


def _clean_env() -> dict[str, str]:
    """The caller's environment minus git's own variables.

    A pre-commit hook runs with GIT_INDEX_FILE, GIT_DIR and friends exported for the
    commit in progress; a git subprocess in a temp repo inherits them and operates
    on the wrong repository ("commit --allow-empty" then fails). The tools-tests
    hook runs this file on every commit that touches tools/, so scrub them.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, env=_clean_env(), check=True, capture_output=True, text=True
    )


def _in_place(env_value: str | None) -> int:
    env = {k: v for k, v in _clean_env().items() if k != "ARXII_BRANCH_IN_PLACE"}
    if env_value is not None:
        env["ARXII_BRANCH_IN_PLACE"] = env_value
    result = subprocess.run(
        ["bash", "-c", f'source "{HELPERS}" && wt_branch_in_place'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


@unittest.skipIf(os.name == "nt", "bash helpers and worktree removal; CI runs Linux")
class BranchInPlaceHelperTests(unittest.TestCase):
    def test_explicit_override_wins_in_both_directions(self) -> None:
        self.assertEqual(_in_place("1"), 0)
        self.assertEqual(_in_place("0"), 1)

    def test_default_follows_visible_memory(self) -> None:
        """Under 8 GiB of MemTotal the helper says in place; at or above, worktree."""
        kb = 0
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
        expected = 0 if 0 < kb < 8 * 1024 * 1024 else 1
        self.assertEqual(_in_place(None), expected)


@unittest.skipIf(os.name == "nt", "Windows refuses to delete a process's cwd; CI runs Linux")
class PostMergeCleanupInPlaceTests(unittest.TestCase):
    def test_branch_checked_out_in_main_tree_is_deleted_without_removing_the_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            origin = base / "origin.git"
            main = base / "main"
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
            # The solo-machine shape: the branch is checked out in the main tree.
            _git("checkout", "-b", BRANCH, cwd=main)

            env = _clean_env()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
            result = subprocess.run(
                ["bash", str(CLEANUP), BRANCH, PR],
                cwd=main,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(main.exists())
            head = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=main,
                env=_clean_env(),
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            self.assertEqual(head, "main")
            branches = subprocess.run(
                ["git", "branch", "--list", BRANCH],
                cwd=main,
                env=_clean_env(),
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            self.assertEqual(branches, "")
            summary = json.loads(result.stdout[result.stdout.index("{") :])
            self.assertEqual(summary["branch_deleted"], BRANCH)
