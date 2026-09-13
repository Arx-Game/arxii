"""The no-clearing pre-commit hook keeps other agents' work on disk (#3814).

pre-commit's generated hook runs ``git checkout -- .`` over the whole worktree while a
commit's hooks run, so a second agent sharing the worktree loses its uncommitted edits
for that window and can lose anything it writes during it. ``tools/githooks/pre-commit``
checks the staged files with ``pre-commit run --files`` instead, which never stashes.

These tests drive real ``git commit`` calls in a temporary repo. The ``gate`` hook holds
a commit open until the test creates a ``go`` file, so a "sibling agent" can act in the
middle of the hooks deterministically, with no sleeps.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "tools/githooks/pre-commit"
INSTALL = ROOT / "tools/githooks/install.sh"

_FIXER = """#!/usr/bin/env bash
for f in "$@"; do sed -i 's/[ ]*$//' "$f"; done
"""

_FAILER = """#!/usr/bin/env bash
if grep -q FAIL "$@"; then echo "found FAIL"; exit 1; fi
"""

_GATE = """#!/usr/bin/env bash
[ -n "${GATE_DIR:-}" ] || exit 0
touch "$GATE_DIR/started"
for _ in $(seq 150); do
  [ -e "$GATE_DIR/go" ] && exit 0
  sleep 0.1
done
exit 0
"""

_GROWER = """#!/usr/bin/env bash
[ -n "${GROW:-}" ] || exit 0
for f in "$@"; do echo x >>"$f"; done
"""

_CONFIG = """repos:
- repo: local
  hooks:
  - id: fixer
    name: fixer
    entry: {hooks}/fixer.sh
    language: system
    files: \\.txt$
  - id: failer
    name: failer
    entry: {hooks}/failer.sh
    language: system
    files: \\.txt$
  - id: gate
    name: gate
    entry: {hooks}/gate.sh
    language: system
    pass_filenames: false
    files: \\.txt$
  - id: grower
    name: grower
    entry: {hooks}/grower.sh
    language: system
    files: \\.txt$
"""


def _clean_env(**extra: str) -> dict[str, str]:
    """The environment for commands in the temporary repo.

    This suite also runs inside a real commit (the ``tools-tests`` hook), which exports
    ``GIT_DIR``, ``GIT_INDEX_FILE``, ``SKIP`` and pre-commit's own variables. Any of them
    leaking in would point the temporary repo's git and pre-commit at the real one.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "PRE_COMMIT")) and key != "SKIP"
    }
    env.update(extra)
    return env


class NoClearingHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.repo = base / "repo"
        self.hooks = base / "hooks"
        self.gate = base / "gate"
        self.pre_commit_home = base / "pre-commit-home"
        for directory in (self.repo, self.hooks, self.gate):
            directory.mkdir()
        scripts = (
            ("fixer.sh", _FIXER),
            ("failer.sh", _FAILER),
            ("gate.sh", _GATE),
            ("grower.sh", _GROWER),
        )
        for name, script in scripts:
            path = self.hooks / name
            path.write_text(script, encoding="utf-8")
            path.chmod(0o755)

        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        config = _CONFIG.format(hooks=self.hooks)
        (self.repo / ".pre-commit-config.yaml").write_text(config, encoding="utf-8")
        self.write("a.txt", "base\n")
        self.write("b.txt", "base\n")
        tracked_hook = self.repo / "tools/githooks/pre-commit"
        tracked_hook.parent.mkdir(parents=True)
        shutil.copy2(HOOK, tracked_hook)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.install()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            env=_clean_env(),
            capture_output=True,
            text=True,
            check=check,
        )

    def install(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(INSTALL)],
            cwd=self.repo,
            env=_clean_env(PRE_COMMIT_PYTHON=sys.executable),
            capture_output=True,
            text=True,
            check=True,
        )

    def commit_env(self, **extra: str) -> dict[str, str]:
        return _clean_env(PRE_COMMIT_HOME=str(self.pre_commit_home), **extra)

    def commit(self, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "commit", *(args or ("-m", "change"))],
            cwd=self.repo,
            env=self.commit_env(**extra),
            capture_output=True,
            text=True,
            check=False,
        )

    def start_gated_commit(self, *args: str) -> subprocess.Popen[str]:
        """Start a commit and return once its hooks are running (the gate has started)."""
        process = subprocess.Popen(
            ["git", "commit", *(args or ("-m", "change"))],
            cwd=self.repo,
            env=self.commit_env(GATE_DIR=str(self.gate)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + 60
        while not (self.gate / "started").exists():
            if process.poll() is not None or time.monotonic() > deadline:
                output = process.communicate()[0]
                message = f"commit never reached the gate hook:\n{output}"
                raise AssertionError(message)
            time.sleep(0.05)
        return process

    def release(self, process: subprocess.Popen[str]) -> tuple[int, str]:
        (self.gate / "go").touch()
        output, _ = process.communicate(timeout=120)
        return process.returncode, output

    def write(self, name: str, text: str) -> None:
        (self.repo / name).write_text(text, encoding="utf-8")

    def read(self, name: str) -> str:
        return (self.repo / name).read_text(encoding="utf-8")

    def head_sha(self) -> str:
        return self.git("rev-parse", "HEAD").stdout.strip()

    def head_files(self) -> list[str]:
        return self.git("show", "--name-only", "--format=", "HEAD").stdout.split()

    def test_stock_hook_loses_a_sibling_write_during_hooks(self) -> None:
        """Control: with no tracked hook, the shim runs pre-commit's own hook and the bug shows."""
        self.git("rm", "-q", "tools/githooks/pre-commit")
        self.git("commit", "-q", "--no-verify", "-m", "drop the tracked hook")
        self.write("b.txt", "base\nB-early\n")
        self.write("a.txt", "base\nA\n")
        self.git("add", "a.txt")

        process = self.start_gated_commit()
        self.assertNotIn("B-early", self.read("b.txt"))
        self.write("b.txt", "base\nB-early\nB-mid\n")
        returncode, output = self.release(process)

        self.assertNotEqual(returncode, 0, output)
        self.assertNotIn("B-mid", self.read("b.txt"))

    def test_clean_commit_passes(self) -> None:
        self.write("a.txt", "base\nA\n")
        self.git("add", "a.txt")

        result = self.commit()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git("show", "HEAD:a.txt").stdout, "base\nA\n")

    def test_sibling_unstaged_edit_stays_on_disk_while_hooks_run(self) -> None:
        self.write("b.txt", "base\nB-early\n")
        self.write("a.txt", "base\nA\n")
        self.git("add", "a.txt")

        process = self.start_gated_commit()
        self.assertIn("B-early", self.read("b.txt"))
        returncode, output = self.release(process)

        self.assertEqual(returncode, 0, output)
        self.assertEqual(self.read("b.txt"), "base\nB-early\n")
        self.assertEqual(self.head_files(), ["a.txt"])

    def test_tracked_hook_runs_without_its_executable_bit(self) -> None:
        """core.fileMode=false can check the script out without +x; the shim must not fall back."""
        (self.repo / "tools/githooks/pre-commit").chmod(0o644)
        self.write("b.txt", "base\nB-early\n")
        self.write("a.txt", "base\nA\n")
        self.git("add", "a.txt")

        process = self.start_gated_commit()
        self.assertIn("B-early", self.read("b.txt"))
        returncode, output = self.release(process)

        self.assertEqual(returncode, 0, output)
        self.assertEqual(self.head_files(), ["a.txt"])

    def test_sibling_write_during_hooks_is_not_a_failure(self) -> None:
        self.write("b.txt", "base\nB-early\n")
        self.write("a.txt", "base\nA\n")
        self.git("add", "a.txt")

        process = self.start_gated_commit()
        self.write("b.txt", "base\nB-early\nB-mid\n")
        returncode, output = self.release(process)

        self.assertEqual(returncode, 0, output)
        self.assertIn("treating as pass", output)
        self.assertEqual(self.read("b.txt"), "base\nB-early\nB-mid\n")
        self.assertEqual(self.head_files(), ["a.txt"])

    def test_auto_fix_of_fully_staged_file_lands_in_the_same_commit(self) -> None:
        self.write("a.txt", "base\nA   \n")
        self.git("add", "a.txt")

        result = self.commit()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("re-staged", result.stdout + result.stderr)
        self.assertEqual(self.git("show", "HEAD:a.txt").stdout, "base\nA\n")
        self.assertEqual(self.git("status", "--short").stdout, "")

    def test_auto_fix_of_partly_staged_file_refuses(self) -> None:
        self.write("a.txt", "l1\nl2\nl3\nl4\nl5\nl6\n")
        self.git("add", "a.txt")
        self.git("commit", "-q", "--no-verify", "-m", "six lines")
        head = self.head_sha()
        self.write("a.txt", "l1 staged   \nl2\nl3\nl4\nl5\nl6\n")
        self.git("add", "a.txt")
        self.write("a.txt", "l1 staged   \nl2\nl3\nl4\nl5\nl6 unstaged\n")

        result = self.commit()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("a.txt was partially staged", result.stdout + result.stderr)
        self.assertEqual(self.head_sha(), head)
        self.assertIn("l1 staged", self.read("a.txt"))
        self.assertIn("l6 unstaged", self.read("a.txt"))

    def test_real_hook_failure_blocks_the_commit_and_touches_nothing(self) -> None:
        self.write("b.txt", "base\nB-early\n")
        self.write("a.txt", "base\nFAIL\n")
        self.git("add", "a.txt")
        head = self.head_sha()

        result = self.commit()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("- exit code: 1", result.stdout + result.stderr)
        self.assertEqual(self.head_sha(), head)
        self.assertEqual(self.read("b.txt"), "base\nB-early\n")

    def test_skip_passes_through_to_pre_commit(self) -> None:
        self.write("a.txt", "base\nFAIL\n")
        self.git("add", "a.txt")

        result = self.commit(SKIP="failer")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installer_is_idempotent_and_leaves_pre_push_alone(self) -> None:
        hooks_dir = self.repo / ".git/hooks"
        pre_push = hooks_dir / "pre-push"
        pre_push.write_text("#!/bin/sh\necho sentinel\n", encoding="utf-8")
        self.git("config", "core.hooksPath", "/nonexistent/windows/path")
        first = (hooks_dir / "pre-commit").read_text(encoding="utf-8")

        self.install()
        self.install()

        self.assertEqual((hooks_dir / "pre-commit").read_text(encoding="utf-8"), first)
        self.assertTrue(os.access(hooks_dir / "pre-commit", os.X_OK))
        self.assertEqual(pre_push.read_text(encoding="utf-8"), "#!/bin/sh\necho sentinel\n")
        hooks_path = self.git("config", "--get", "core.hooksPath", check=False)
        self.assertEqual(hooks_path.returncode, 1)

    def test_pathspec_commit_keeps_a_sibling_out_of_the_index_during_hooks(self) -> None:
        """A pathspec commit holds index.lock while hooks run, so a sibling cannot mix in."""
        self.write("a.txt", "base\nA\n")
        self.write("b.txt", "base\nB\n")

        process = self.start_gated_commit("-m", "A", "--", "a.txt")
        sibling = subprocess.run(
            ["git", "commit", "-m", "B", "--", "b.txt"],
            cwd=self.repo,
            env=self.commit_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        returncode, output = self.release(process)

        self.assertNotEqual(sibling.returncode, 0, sibling.stdout + sibling.stderr)
        self.assertIn("index.lock", sibling.stderr)
        self.assertEqual(returncode, 0, output)
        self.assertEqual(self.head_files(), ["a.txt"])
        retry = self.commit("-m", "B", "--", "b.txt")
        self.assertEqual(retry.returncode, 0, retry.stdout + retry.stderr)
        self.assertEqual(self.head_files(), ["b.txt"])

    def test_auto_fix_in_a_pathspec_commit_asks_for_the_same_commit_again(self) -> None:
        """Re-staging in git's temporary index never reaches the real one, so refuse instead."""
        self.write("a.txt", "base\nA   \n")
        head = self.head_sha()

        first = self.commit("-m", "change", "--", "a.txt")

        self.assertNotEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("re-run the same git commit", first.stdout + first.stderr)
        self.assertEqual(self.head_sha(), head)
        self.assertEqual(self.read("a.txt"), "base\nA\n")
        self.assertEqual(self.git("diff", "--cached", "--name-only").stdout, "")

        second = self.commit("-m", "change", "--", "a.txt")

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(self.git("show", "HEAD:a.txt").stdout, "base\nA\n")
        self.assertEqual(self.git("status", "--short").stdout, "")

    def test_retry_cap_refuses_without_staging_its_last_fix(self) -> None:
        self.write("a.txt", "base\nA\n")
        self.git("add", "a.txt")
        head = self.head_sha()

        result = self.commit(GROW="1")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("after 3 attempts", result.stdout + result.stderr)
        self.assertEqual(self.head_sha(), head)
        self.assertEqual(self.git("show", ":a.txt").stdout.count("x\n"), 2)
        self.assertEqual(self.read("a.txt").count("x\n"), 3)


if __name__ == "__main__":
    unittest.main()
