"""Tests for the player channels models and the tenure speaker name (#3299)."""

from django.test import TestCase

from world.roster.factories import RosterTenureFactory


class SpeakerNameTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.first = RosterTenureFactory(player_number=1)
        name = cls.first.roster_entry.character_sheet.character.name
        cls.name = name
        entry = cls.first.roster_entry
        cls.second = RosterTenureFactory(roster_entry=entry, player_number=2)
        cls.eleventh = RosterTenureFactory(roster_entry=entry, player_number=11)

    def test_first_player_speaks_as_bare_character_name(self) -> None:
        self.assertEqual(self.first.speaker_name, self.name)

    def test_later_players_get_ordinal_form(self) -> None:
        self.assertEqual(self.second.speaker_name, f"2nd player of {self.name}")
        self.assertEqual(self.eleventh.speaker_name, f"11th player of {self.name}")
