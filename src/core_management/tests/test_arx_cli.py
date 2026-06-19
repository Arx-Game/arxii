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
