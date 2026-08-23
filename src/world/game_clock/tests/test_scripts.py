"""Tests for the GameTickScript."""

from unittest.mock import MagicMock, patch

from django.test import TestCase


class GameTickRepeatTests(TestCase):
    @patch("world.game_clock.scripts.run_due_tasks")
    @patch("world.game_clock.scripts.get_ic_now")
    @patch("world.game_clock.scripts.close_old_connections")
    def test_at_repeat_heals_connections_before_any_query(
        self, mock_close: MagicMock, mock_ic_now: MagicMock, mock_run: MagicMock
    ) -> None:
        """close_old_connections runs FIRST — before get_ic_now's query.

        Ordering is the contract: a dead connection (Postgres restarted under
        the long-lived Server) must be discarded before the tick's first
        query, or the tick raises OperationalError forever (2026-08-23
        reload-wedge incident).
        """
        from world.game_clock.scripts import GameTickScript

        call_order: list[str] = []
        mock_close.side_effect = lambda: call_order.append("close")
        mock_ic_now.side_effect = lambda: call_order.append("ic_now")
        mock_run.return_value = []

        GameTickScript.at_repeat(MagicMock())
        self.assertEqual(call_order[0], "close")
        self.assertIn("ic_now", call_order)


class EnsureGameTickScriptTests(TestCase):
    @patch("world.game_clock.scripts.GameTickScript")
    def test_skips_creation_when_exists(self, mock_gts: MagicMock) -> None:
        """Does not create a new script if one exists."""
        from world.game_clock.scripts import ensure_game_tick_script

        mock_gts.objects.first.return_value = MagicMock()
        ensure_game_tick_script()
        mock_gts.objects.first.assert_called_once()

    @patch("evennia.utils.create.create_script")
    @patch("world.game_clock.scripts.GameTickScript")
    def test_creates_when_not_exists(self, mock_gts: MagicMock, mock_create: MagicMock) -> None:
        """Creates the script if it doesn't exist."""
        from world.game_clock.scripts import ensure_game_tick_script

        mock_gts.objects.first.return_value = None
        ensure_game_tick_script()
        mock_create.assert_called_once()
