"""Tests for the GameTickScript."""

from unittest.mock import MagicMock, patch

from django.test import TestCase


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
