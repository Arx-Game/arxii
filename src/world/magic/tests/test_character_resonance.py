"""Tests for the merged CharacterResonance shape (Spec A §2.2).

After Phase 9 of the resonance pivot, CharacterResonance is the single
per-character per-resonance row, carrying both identity (the row exists)
and currency (`balance` + `lifetime_earned`). The `is_active`, `scope`,
`strength`, and `created_at` fields are gone; the FK is to CharacterSheet,
not ObjectDB.
"""

from django.db.utils import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.magic.models import CharacterResonance


class CharacterResonanceMergedShapeTests(TestCase):
    """Verify the new field set, FK target, and unique constraint."""

    def test_fields_balance_lifetime_claimed_at(self) -> None:
        cr = CharacterResonanceFactory(balance=5, lifetime_earned=12)
        self.assertEqual(cr.balance, 5)
        self.assertEqual(cr.lifetime_earned, 12)
        self.assertIsNotNone(cr.claimed_at)

    def test_unique_together_character_sheet_resonance(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        CharacterResonance.objects.create(character_sheet=sheet, resonance=res)
        # Use .objects.create() to bypass the factory's django_get_or_create
        # and exercise the DB-level unique constraint.
        with self.assertRaises(IntegrityError):
            CharacterResonance.objects.create(character_sheet=sheet, resonance=res)

    def test_dropped_fields_absent(self) -> None:
        # is_active, scope, strength must be gone
        field_names = {f.name for f in CharacterResonance._meta.get_fields()}
        for dropped in ("is_active", "scope", "strength"):
            self.assertNotIn(dropped, field_names, f"{dropped} should be removed")

    def test_character_field_renamed_to_character_sheet(self) -> None:
        field_names = {f.name for f in CharacterResonance._meta.get_fields()}
        self.assertIn("character_sheet", field_names)
        self.assertNotIn("character", field_names)

    def test_str_uses_character_sheet(self) -> None:
        cr = CharacterResonanceFactory()
        rendered = str(cr)
        self.assertIn(cr.resonance.name, rendered)
