"""Tests for the GameTickScript."""

from unittest.mock import MagicMock, patch

from django.test import TestCase


class EnsureGameTickScriptTests(TestCase):
    @patch("evennia.scripts.models.ScriptDB")
    def test_skips_creation_when_exists(self, mock_script_db: MagicMock) -> None:
        """Does not create a new script if one exists."""
        from world.game_clock.scripts import ensure_game_tick_script

        mock_script_db.objects.filter.return_value.exists.return_value = True
        ensure_game_tick_script()
        mock_script_db.objects.filter.assert_called_once()

    @patch("evennia.utils.create.create_script")
    @patch("evennia.scripts.models.ScriptDB")
    def test_creates_when_not_exists(
        self, mock_script_db: MagicMock, mock_create: MagicMock
    ) -> None:
        """Creates the script if it doesn't exist."""
        from world.game_clock.scripts import ensure_game_tick_script

        mock_script_db.objects.filter.return_value.exists.return_value = False
        ensure_game_tick_script()
        mock_create.assert_called_once()
