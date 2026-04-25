"""Tests for CharacterSheet.get_corruption_stage + is_protagonism_locked (Scope #7)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import ResonanceFactory, with_corruption_at_stage


class TestGetCorruptionStage(TestCase):
    """CharacterSheet.get_corruption_stage(resonance) returns 0-5."""

    def test_returns_zero_when_no_condition(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        self.assertEqual(sheet.get_corruption_stage(resonance), 0)

    def test_returns_stage_when_condition_exists(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with_corruption_at_stage(sheet, resonance, stage=2)
        self.assertEqual(sheet.get_corruption_stage(resonance), 2)

    def test_returns_stage_5_at_terminal(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with_corruption_at_stage(sheet, resonance, stage=5)
        self.assertEqual(sheet.get_corruption_stage(resonance), 5)

    def test_returns_stage_1_at_entry(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with_corruption_at_stage(sheet, resonance, stage=1)
        self.assertEqual(sheet.get_corruption_stage(resonance), 1)

    def test_different_resonances_are_independent(self) -> None:
        sheet = CharacterSheetFactory()
        resonance_a = ResonanceFactory()
        resonance_b = ResonanceFactory()
        with_corruption_at_stage(sheet, resonance_a, stage=3)
        self.assertEqual(sheet.get_corruption_stage(resonance_b), 0)


class TestIsProtagonismLocked(TestCase):
    """CharacterSheet.is_protagonism_locked cached_property."""

    def test_false_by_default(self) -> None:
        sheet = CharacterSheetFactory()
        self.assertFalse(sheet.is_protagonism_locked)

    def test_false_at_stage_4(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with_corruption_at_stage(sheet, resonance, stage=4)
        # Reload to reset cached_property
        from world.character_sheets.models import CharacterSheet

        fresh = CharacterSheet.objects.get(pk=sheet.pk)
        self.assertFalse(fresh.is_protagonism_locked)

    def test_true_at_stage_5(self) -> None:
        from world.character_sheets.models import CharacterSheet

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with_corruption_at_stage(sheet, resonance, stage=5)
        # Reload to clear cached_property
        fresh = CharacterSheet.objects.get(pk=sheet.pk)
        self.assertTrue(fresh.is_protagonism_locked)

    def test_cached_property_invalidation_via_dict_pop(self) -> None:
        """Mutating __dict__ correctly invalidates cached_property."""

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        # Prime the cache (False)
        self.assertFalse(sheet.is_protagonism_locked)
        # Now add stage 5
        with_corruption_at_stage(sheet, resonance, stage=5)
        # Pop the cached value
        sheet.__dict__.pop("is_protagonism_locked", None)
        # Should now reflect the new state
        self.assertTrue(sheet.is_protagonism_locked)
