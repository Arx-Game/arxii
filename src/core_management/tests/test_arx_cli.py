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
