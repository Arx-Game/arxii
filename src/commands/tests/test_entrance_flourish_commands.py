"""Unit tests for the _resolve_resonance command helper (#1339).

The E2E test covers the happy path. These cover the fiddly branching:
numeric ID first, name fallback, and the claimed-resonance list on miss.
"""

from __future__ import annotations

from django.test import TestCase, tag

from commands.exceptions import CommandError
from commands.social.entrance_flourish import _resolve_resonance
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory


@tag("postgres")
class ResolveResonanceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.bare_sheet = CharacterSheetFactory()  # no claimed resonances
        cls.embers = ResonanceFactory(name="Embers")
        cls.frost = ResonanceFactory(name="Frost")
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.embers)
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.frost)

    def test_numeric_resolves_by_pk(self) -> None:
        result = _resolve_resonance(str(self.embers.pk), self.sheet)
        self.assertEqual(result, self.embers)

    def test_name_case_insensitive(self) -> None:
        result = _resolve_resonance("embers", self.sheet)
        self.assertEqual(result, self.embers)

    def test_name_exact_case(self) -> None:
        result = _resolve_resonance("Frost", self.sheet)
        self.assertEqual(result, self.frost)

    def test_numeric_falls_back_to_name_on_pk_miss(self) -> None:
        # A non-existent PK that happens to match no name either → error listing claimed resonances
        with self.assertRaises(CommandError) as ctx:
            _resolve_resonance("999999", self.sheet)
        self.assertIn("Embers", ctx.exception.msg)
        self.assertIn("Frost", ctx.exception.msg)

    def test_unknown_name_lists_claimed_resonances(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            _resolve_resonance("Shadow", self.sheet)
        self.assertIn("Embers", ctx.exception.msg)
        self.assertIn("Frost", ctx.exception.msg)

    def test_sheet_with_no_claimed_resonances(self) -> None:
        # cls.bare_sheet has no CharacterResonance rows; "zzz_no_such_resonance_xyz"
        # does not exist in the DB — so the "no claimed resonances" branch is taken.
        with self.assertRaises(CommandError) as ctx:
            _resolve_resonance("zzz_no_such_resonance_xyz", self.bare_sheet)
        self.assertIn("no claimed resonances", ctx.exception.msg.lower())
