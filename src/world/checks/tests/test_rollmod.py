"""Tests for rollmod fields."""

from django.test import TestCase

from evennia_extensions.models import PlayerData
from world.character_sheets.models import CharacterSheet


class RollmodFieldTests(TestCase):
    """Test that rollmod fields exist and default to 0."""

    def test_character_sheet_has_rollmod(self):
        assert hasattr(CharacterSheet, "rollmod")

    def test_player_data_has_rollmod(self):
        assert hasattr(PlayerData, "rollmod")

    def test_character_sheet_rollmod_default(self):
        field = CharacterSheet._meta.get_field("rollmod")
        assert field.default == 0

    def test_player_data_rollmod_default(self):
        field = PlayerData._meta.get_field("rollmod")
        assert field.default == 0
