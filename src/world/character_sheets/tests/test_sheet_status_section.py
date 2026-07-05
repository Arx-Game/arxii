"""Tests for the telnet ``sheet/status`` section (#1446 bundle 2).

Telnet parity for the web Status panel — health/stamina/anima render as words
(never raw numbers), plus coin and AP-remaining lines over the same services.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.account.sheet_sections import SHEET_SECTIONS
from world.character_sheets.factories import CharacterFactory, CharacterSheetFactory
from world.currency.services import get_or_create_purse
from world.vitals.factories import CharacterVitalsFactory


def _command_for(character) -> MagicMock:
    command = MagicMock()
    command.caller.puppet = character
    command.args = ""
    return command


class SheetStatusSectionTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_registered(self) -> None:
        self.assertIn("status", SHEET_SECTIONS)

    def test_wounded_character_renders_words_not_numbers(self) -> None:
        CharacterVitalsFactory(character_sheet=self.sheet, health=50, max_health=100)

        lines = SHEET_SECTIONS["status"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertIn("wounded", text)  # WOUND_DESCRIPTIONS band word
        self.assertNotIn("50", text.replace("50c", ""))  # no raw health numbers
        self.assertNotIn("100", text)

    def test_renders_coin_and_ap_lines(self) -> None:
        purse = get_or_create_purse(self.sheet)
        purse.balance = 1234
        purse.save(update_fields=["balance"])

        lines = SHEET_SECTIONS["status"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertIn("12g 3s 4c", text)
        self.assertIn("AP", text)

    def test_default_character_renders_sane_defaults(self) -> None:
        lines = SHEET_SECTIONS["status"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertTrue(len(lines) >= 3)
        self.assertIn("0c", text)  # empty purse
