"""Tests for the telnet ``sheet/distinction`` and ``sheet/magic`` sections (#1446).

Telnet parity for the web Distinctions and Magic (spellbook) tabs — both faces read the
same ``_build_distinctions`` / ``_build_magic`` builders, so they can't drift.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.account.sheet_sections import SHEET_SECTIONS
from world.character_sheets.factories import CharacterFactory, CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ResonanceFactory,
)
from world.secrets.factories import SecretFactory


def _command_for(character) -> MagicMock:
    command = MagicMock()
    command.caller.puppet = character
    command.args = ""
    return command


class SheetDistinctionSectionTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_registered_with_aliases(self) -> None:
        self.assertIn("distinction", SHEET_SECTIONS)
        self.assertIn("distinctions", SHEET_SECTIONS)
        self.assertIn("magic", SHEET_SECTIONS)

    def test_lists_distinctions_with_rank_and_secret_marker(self) -> None:
        public = CharacterDistinctionFactory(
            character=self.sheet,
            distinction=DistinctionFactory(name="Silver Tongue"),
            rank=2,
        )
        hidden = CharacterDistinctionFactory(
            character=self.sheet,
            distinction=DistinctionFactory(name="Blood Debt"),
            rank=1,
            secret=SecretFactory(),
        )

        lines = SHEET_SECTIONS["distinction"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertIn(public.distinction.name, text)
        self.assertIn("rank 2", text)
        self.assertIn(hidden.distinction.name, text)  # owner sees gated entries
        self.assertIn("(secret)", text)

    def test_empty_state(self) -> None:
        lines = SHEET_SECTIONS["distinction"](_command_for(self.character))
        self.assertEqual(lines, ["You have no distinctions."])


class SheetMagicSectionTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_lists_gifts(self) -> None:
        gift_row = CharacterGiftFactory(
            character=self.sheet,
            gift=GiftFactory(name="Emberweaving"),
        )

        lines = SHEET_SECTIONS["magic"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertIn(gift_row.gift.name, text)

    def test_empty_state(self) -> None:
        lines = SHEET_SECTIONS["magic"](_command_for(self.character))
        self.assertEqual(lines, ["Nothing is known of your magic."])

    def test_lists_resonance_balances(self) -> None:
        """#2032 — claimed resonances render with balance + lifetime earned."""
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=ResonanceFactory(name="Ember"),
            balance=15,
            lifetime_earned=40,
        )

        lines = SHEET_SECTIONS["magic"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertIn("Ember", text)
        self.assertIn("15", text)
        self.assertIn("40", text)
