"""Unit tests for the arx CLI (src/cli/arx.py) subprocess wiring.

These tests patch subprocess.run to verify command construction without
touching the database or spawning real processes.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

# Make the cli module importable regardless of sys.path state.
_CLI_DIR = Path(__file__).resolve().parent.parent.parent / "cli"
if str(_CLI_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR.parent))


class TestSeedCLICommand(unittest.TestCase):
    """Verify that `arx seed` forwards the correct argv to subprocess.run."""

    def _invoke_seed(self, *cli_args: str) -> mock.MagicMock:
        """Call the seed() function with subprocess.run patched; return the mock."""
        from typer.testing import CliRunner

        # Import lazily so path insertion above takes effect first.
        from cli.arx import app

        runner = CliRunner()
        with mock.patch("cli.arx.subprocess.run") as mock_run, mock.patch("cli.arx.setup_env"):
            mock_run.return_value = mock.MagicMock(returncode=0)
            result = runner.invoke(app, ["seed", *cli_args], catch_exceptions=False)
        # Re-raise if Typer itself errored so the test message is clear.
        if result.exception:
            raise result.exception
        return mock_run

    def test_seed_default_target_is_dev(self) -> None:
        """arx seed  (no arg) → evennia seed dev"""
        mock_run = self._invoke_seed()
        mock_run.assert_called_once_with(["evennia", "seed", "dev"], check=True)

    def test_seed_explicit_dev_target(self) -> None:
        """arx seed dev → evennia seed dev"""
        mock_run = self._invoke_seed("dev")
        mock_run.assert_called_once_with(["evennia", "seed", "dev"], check=True)

    def test_seed_custom_target_forwarded(self) -> None:
        """arx seed staging → evennia seed staging (custom target forwarded)"""
        mock_run = self._invoke_seed("staging")
        mock_run.assert_called_once_with(["evennia", "seed", "staging"], check=True)


class TestParallelWorkerCount(unittest.TestCase):
    """Verify that parallel test workers are capped by memory, not just core count.

    A bare ``--parallel`` resolves to cpu_count() inside Django, which exhausts a
    memory-capped devcontainer: each worker holds a full Django+Evennia stack.
    """

    def test_memory_caps_below_core_count(self) -> None:
        """8 cores but only 1GB available → 2 workers, not 8."""
        from cli.arx import _parallel_worker_count

        with (
            mock.patch("cli.arx.os.cpu_count", return_value=8),
            mock.patch("cli.arx._available_memory_mb", return_value=1000),
            mock.patch.dict("cli.arx.os.environ", {}, clear=True),
        ):
            self.assertEqual(_parallel_worker_count(), 2)

    def test_core_count_caps_below_memory(self) -> None:
        """Ample memory must not push worker count above the core count."""
        from cli.arx import _parallel_worker_count

        with (
            mock.patch("cli.arx.os.cpu_count", return_value=8),
            mock.patch("cli.arx._available_memory_mb", return_value=100_000),
            mock.patch.dict("cli.arx.os.environ", {}, clear=True),
        ):
            self.assertEqual(_parallel_worker_count(), 8)

    def test_never_returns_zero_under_memory_pressure(self) -> None:
        """Near-zero available memory still yields a usable single worker."""
        from cli.arx import _parallel_worker_count

        with (
            mock.patch("cli.arx.os.cpu_count", return_value=8),
            mock.patch("cli.arx._available_memory_mb", return_value=10),
            mock.patch.dict("cli.arx.os.environ", {}, clear=True),
        ):
            self.assertEqual(_parallel_worker_count(), 1)

    def test_falls_back_to_core_count_without_meminfo(self) -> None:
        """Platforms with no /proc/meminfo (Windows) keep the old behaviour."""
        from cli.arx import _parallel_worker_count

        with (
            mock.patch("cli.arx.os.cpu_count", return_value=4),
            mock.patch("cli.arx._available_memory_mb", return_value=None),
            mock.patch.dict("cli.arx.os.environ", {}, clear=True),
        ):
            self.assertEqual(_parallel_worker_count(), 4)

    def test_env_override_wins(self) -> None:
        """ARX_TEST_MAX_WORKERS overrides the derived value."""
        from cli.arx import _parallel_worker_count

        with (
            mock.patch("cli.arx.os.cpu_count", return_value=8),
            mock.patch("cli.arx._available_memory_mb", return_value=100_000),
            mock.patch.dict("cli.arx.os.environ", {"ARX_TEST_MAX_WORKERS": "3"}, clear=True),
        ):
            self.assertEqual(_parallel_worker_count(), 3)

    def test_unparseable_env_override_degrades_to_default(self) -> None:
        """A bad env var must not break every test invocation."""
        from cli.arx import _parallel_worker_count

        with (
            mock.patch("cli.arx.os.cpu_count", return_value=8),
            mock.patch("cli.arx._available_memory_mb", return_value=100_000),
            mock.patch.dict("cli.arx.os.environ", {"ARX_TEST_MAX_WORKERS": "lots"}, clear=True),
        ):
            self.assertEqual(_parallel_worker_count(), 8)

    def test_parallel_flag_emits_explicit_worker_count(self) -> None:
        """arx test --parallel → evennia test --parallel=N, never a bare --parallel."""
        from typer.testing import CliRunner

        from cli.arx import app

        runner = CliRunner()
        with (
            mock.patch("cli.arx.subprocess.run") as mock_run,
            mock.patch("cli.arx.setup_env"),
            mock.patch("cli.arx._parallel_worker_count", return_value=3),
        ):
            mock_run.return_value = mock.MagicMock(returncode=0)
            runner.invoke(app, ["test", "--parallel"])

        command = mock_run.call_args[0][0]
        self.assertIn("--parallel=3", command)
        self.assertNotIn("--parallel", command)


class TestRewriteEnvKeys(unittest.TestCase):
    """`_rewrite_env_keys` updates keys in place and refuses line-spanning values."""

    def setUp(self) -> None:
        import tempfile

        self.dir = Path(tempfile.mkdtemp())
        self.env = self.dir / ".env"

    def test_replaces_an_existing_key_in_place(self) -> None:
        from cli.arx import _rewrite_env_keys

        self.env.write_text("A=1\nFRONTEND_URL=old\nB=2\n")
        _rewrite_env_keys(self.env, {"FRONTEND_URL": "new"})
        self.assertEqual(self.env.read_text(), "A=1\nFRONTEND_URL=new\nB=2\n")

    def test_appends_a_key_that_is_not_present(self) -> None:
        from cli.arx import _rewrite_env_keys

        self.env.write_text("A=1\n")
        _rewrite_env_keys(self.env, {"B": "2"})
        self.assertIn("B=2\n", self.env.read_text())
        self.assertIn("A=1\n", self.env.read_text())

    def test_refuses_a_value_containing_a_newline(self) -> None:
        """A newline would let the tail land in .env as its own setting."""
        from cli.arx import _rewrite_env_keys

        self.env.write_text("A=1\n")
        with self.assertRaises(ValueError):
            _rewrite_env_keys(self.env, {"FRONTEND_URL": "https://x\nSECRET_KEY=pwned"})
        self.assertEqual(self.env.read_text(), "A=1\n", "the file must be left untouched")

    def test_refuses_a_value_containing_a_carriage_return(self) -> None:
        from cli.arx import _rewrite_env_keys

        self.env.write_text("A=1\n")
        with self.assertRaises(ValueError):
            _rewrite_env_keys(self.env, {"FRONTEND_URL": "https://x\rSECRET_KEY=pwned"})
        self.assertEqual(self.env.read_text(), "A=1\n")


class TestEnvBackupRoundTrip(unittest.TestCase):
    """Backup then restore must return the file's exact bytes."""

    def test_restores_crlf_bytes_unchanged(self) -> None:
        """A text round-trip would normalise CRLF and lose the original bytes."""
        import tempfile

        from cli.arx import _backup_env_file, _restore_env_file

        d = Path(tempfile.mkdtemp())
        env, backup = d / ".env", d / ".env.ngrok_backup"
        original = b"A=1\r\nB=2\r\n"
        env.write_bytes(original)

        _backup_env_file(env, backup)
        env.write_bytes(b"A=clobbered\n")
        _restore_env_file(env, backup)

        self.assertEqual(env.read_bytes(), original)
        self.assertFalse(backup.exists(), "the backup is consumed by the restore")


class TestCleanupVerdict(unittest.TestCase):
    """`arx start` kills only this checkout's server and portal, never a neighbour's.

    A unit test is the right layer: this is developer tooling with no player path, so no
    journey seam reaches it, and the decision is one pure function over a process's
    command line, working directory and interpreter path.

    Parallel agents each work in a worktree under ``<main>/.claude/worktrees/`` and share
    one machine; the start-up cleanup used to SIGKILL every process whose command line
    mentioned evennia, which ended other agents' test runs with no result (#5240).
    """

    MAIN = Path("/work/arxii")
    WORKTREE = MAIN / ".claude" / "worktrees" / "feature-a"
    OTHER_WORKTREE = MAIN / ".claude" / "worktrees" / "feature-b"

    @staticmethod
    def _twistd(root: Path, name: str) -> str:
        venv = root / ".venv"
        script = venv / "lib/python3.13/site-packages/evennia/server" / name
        return f"{venv}/bin/python {venv}/bin/twistd --python={script} --pidfile={root}/x.pid"

    def _process(self, root: Path, name: str = "server.py", **overrides):
        from cli.arx import _ProcessInfo

        fields = {
            "pid": 100,
            "cmdline": self._twistd(root, name),
            "state": "S",
            "cwd": root / "src",
            "interpreter": root / ".venv" / "bin" / "python",
        }
        fields.update(overrides)
        return _ProcessInfo(**fields)

    def test_own_server_is_killed(self) -> None:
        from cli.arx import _cleanup_verdict

        verdict = _cleanup_verdict(self._process(self.WORKTREE), self.WORKTREE)
        self.assertTrue(verdict.kill)

    def test_own_portal_is_killed(self) -> None:
        from cli.arx import _cleanup_verdict

        verdict = _cleanup_verdict(self._process(self.WORKTREE, "portal.py"), self.WORKTREE)
        self.assertTrue(verdict.kill)

    def test_own_server_is_killed_when_only_the_interpreter_can_be_read(self) -> None:
        from cli.arx import _cleanup_verdict

        proc = self._process(self.WORKTREE, cwd=None)
        self.assertTrue(_cleanup_verdict(proc, self.WORKTREE).kill)

    def test_a_process_whose_cwd_and_interpreter_disagree_is_left_alone(self) -> None:
        """A worktree's server run on the main checkout's venv is not the main checkout's."""
        from cli.arx import _cleanup_verdict

        proc = self._process(self.WORKTREE, interpreter=self.MAIN / ".venv" / "bin" / "python")
        self.assertFalse(_cleanup_verdict(proc, self.MAIN).kill)

    def test_another_worktrees_server_is_left_alone(self) -> None:
        from cli.arx import _cleanup_verdict

        verdict = _cleanup_verdict(self._process(self.OTHER_WORKTREE), self.WORKTREE)
        self.assertFalse(verdict.kill)
        self.assertIn("another checkout", verdict.reason)

    def test_main_checkouts_server_is_left_alone_from_a_worktree(self) -> None:
        from cli.arx import _cleanup_verdict

        verdict = _cleanup_verdict(self._process(self.MAIN), self.WORKTREE)
        self.assertFalse(verdict.kill)

    def test_a_worktrees_server_is_left_alone_from_the_main_checkout(self) -> None:
        """The main checkout contains its worktrees on disk but does not own them."""
        from cli.arx import _cleanup_verdict

        verdict = _cleanup_verdict(self._process(self.WORKTREE), self.MAIN)
        self.assertFalse(verdict.kill)

    def test_the_start_command_and_what_launched_it_are_left_alone(self) -> None:
        """A shell whose command line merely mentions evennia must not be killed."""
        from cli.arx import _cleanup_verdict

        proc = self._process(self.WORKTREE, is_this_start=True)
        verdict = _cleanup_verdict(proc, self.WORKTREE)
        self.assertFalse(verdict.kill)

    @unittest.skipUnless(Path("/proc/self/stat").exists(), "needs a Linux /proc")
    def test_the_start_lineage_holds_this_process_and_its_parent(self) -> None:
        import os

        from cli.arx import _this_start_lineage

        lineage = _this_start_lineage()
        self.assertIn(os.getpid(), lineage)
        self.assertIn(os.getppid(), lineage)

    def test_test_run_in_this_checkout_is_left_alone(self) -> None:
        from cli.arx import _cleanup_verdict

        cmdline = (
            f"{self.WORKTREE}/.venv/bin/python {self.WORKTREE}/.venv/bin/evennia test --settings=x"
        )
        verdict = _cleanup_verdict(self._process(self.WORKTREE, cmdline=cmdline), self.WORKTREE)
        self.assertFalse(verdict.kill)
        self.assertEqual(verdict.reason, "a test run")

    def test_test_run_elsewhere_is_left_alone(self) -> None:
        from cli.arx import _cleanup_verdict

        cmdline = f"{self.OTHER_WORKTREE}/.venv/bin/python evennia test --parallel=3 world.x"
        verdict = _cleanup_verdict(
            self._process(self.OTHER_WORKTREE, cmdline=cmdline), self.WORKTREE
        )
        self.assertFalse(verdict.kill)

    def test_child_of_a_test_run_is_left_alone(self) -> None:
        from cli.arx import _cleanup_verdict

        parent = "python /work/arxii/.venv/bin/arx test world.x"
        proc = self._process(self.WORKTREE, ancestor_cmdlines=("bash -c x", parent))
        verdict = _cleanup_verdict(proc, self.WORKTREE)
        self.assertFalse(verdict.kill)
        self.assertEqual(verdict.reason, "started by a test run")

    def test_zombie_is_left_alone(self) -> None:
        from cli.arx import _cleanup_verdict

        by_state = self._process(self.WORKTREE, state="Z")
        by_name = self._process(self.WORKTREE, cmdline="[twistd] <defunct>", state="")
        self.assertFalse(_cleanup_verdict(by_state, self.WORKTREE).kill)
        self.assertFalse(_cleanup_verdict(by_name, self.WORKTREE).kill)

    def test_unreadable_proc_entry_keeps_the_old_behaviour_for_a_server(self) -> None:
        """No cwd or interpreter (Windows, macOS, vanished pid): stale, as before."""
        from cli.arx import _cleanup_verdict

        proc = self._process(self.OTHER_WORKTREE, state="", cwd=None, interpreter=None)
        self.assertTrue(_cleanup_verdict(proc, self.WORKTREE).kill)

    def test_unreadable_proc_entry_still_spares_a_test_run(self) -> None:
        from cli.arx import _cleanup_verdict

        proc = self._process(
            self.WORKTREE,
            cmdline="python evennia test --settings=x",
            state="",
            cwd=None,
            interpreter=None,
        )
        self.assertFalse(_cleanup_verdict(proc, self.WORKTREE).kill)

    def test_a_pid_with_no_proc_entry_describes_as_unknown(self) -> None:
        from cli.arx import _describe_process

        info = _describe_process({"pid": 2**31 - 2, "cmdline": "python twistd server.py"})
        self.assertIsNone(info.cwd)
        self.assertIsNone(info.interpreter)
        self.assertEqual(info.state, "")
        self.assertEqual(info.ancestor_cmdlines, ())

    @unittest.skipUnless(Path("/proc/self/stat").exists(), "needs a Linux /proc")
    def test_a_live_process_is_described_from_the_real_proc_entries(self) -> None:
        """A real child, launched through a symlink the way a venv's python is."""
        import shutil
        import subprocess
        import tempfile

        from cli.arx import _describe_process

        workdir = Path(tempfile.mkdtemp()).resolve()
        launcher = workdir / "venv" / "bin" / "sleep"
        launcher.parent.mkdir(parents=True)
        launcher.symlink_to(shutil.which("sleep"))
        child = subprocess.Popen([str(launcher), "30"], cwd=workdir)
        try:
            info = _describe_process({"pid": child.pid, "cmdline": "sleep 30"})
        finally:
            child.kill()
            child.wait()
            shutil.rmtree(workdir)

        self.assertEqual(info.cwd, workdir)
        self.assertEqual(info.interpreter, launcher, "the symlink is kept, not resolved")
        self.assertIn(info.state, {"S", "R"})
        self.assertTrue(info.ancestor_cmdlines, "the test process is the child's parent")
        self.assertEqual(info.cmdline, f"{launcher} 30")

    def test_test_run_pattern_ignores_paths_that_merely_contain_the_words(self) -> None:
        from cli.arx import _is_test_run

        self.assertFalse(_is_test_run(self._twistd(Path("/work/arx-test-runs"), "server.py")))
        self.assertTrue(_is_test_run("python /x/bin/evennia --settings=a test world.y"))
        self.assertTrue(_is_test_run("uv run arx test"))
        self.assertTrue(_is_test_run("python src/manage.py test world"))

    def test_cleanup_reports_each_process_and_kills_only_the_verdict_kills(self) -> None:
        from cli.arx import _cleanup_stale_processes

        own = self._process(self.WORKTREE, pid=11)
        neighbour = self._process(self.OTHER_WORKTREE, pid=22)
        with (
            mock.patch("cli.arx.PROJECT_ROOT", self.WORKTREE),
            mock.patch("cli.arx._find_evennia_processes", return_value=[{}, {}]),
            mock.patch("cli.arx._describe_process", side_effect=[own, neighbour]),
            mock.patch("cli.arx._this_start_lineage", return_value=frozenset()),
            mock.patch("cli.arx._kill_process", return_value=True) as kill,
            mock.patch("cli.arx.typer.echo") as echo,
            mock.patch("time.sleep"),
        ):
            killed = _cleanup_stale_processes()

        self.assertEqual(killed, 1)
        kill.assert_called_once_with(11)
        lines = [call.args[0] for call in echo.call_args_list]
        self.assertTrue(any("killed: pid 11 (server)" in line for line in lines))
        self.assertTrue(any("left alone: pid 22 (server)" in line for line in lines))
