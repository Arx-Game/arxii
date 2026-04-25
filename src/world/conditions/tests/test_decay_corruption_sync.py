"""Tests for Task 7.2: decay_condition_severity syncs corruption_current.

Spec §3.4 (passive decay integration): when a Corruption-kind ConditionInstance decays,
CharacterResonance.corruption_current is decremented by the same amount via reduce_corruption
(with _from_decay=True to prevent recursion).
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import decay_condition_severity
from world.magic.factories import ResonanceFactory, with_corruption_at_stage
from world.magic.models.aura import CharacterResonance


class TestDecayCorruptionFieldSync(TestCase):
    """decay_condition_severity syncs corruption_current for Corruption-kind conditions."""

    def test_decay_decrements_corruption_current_for_corruption_kind(self) -> None:
        """When a Corruption ConditionInstance decays, CharacterResonance.corruption_current
        is decremented by the same amount."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        instance = with_corruption_at_stage(sheet, resonance, stage=2)

        char_res = CharacterResonance.objects.get(
            character_sheet=sheet,
            resonance=resonance,
        )
        initial = char_res.corruption_current
        self.assertGreater(initial, 0)

        decay_condition_severity(instance, amount=10)

        char_res.refresh_from_db()
        self.assertEqual(char_res.corruption_current, initial - 10)

    def test_decay_clamps_corruption_current_at_zero(self) -> None:
        """If decay amount exceeds corruption_current, it clamps to 0 — not negative."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        instance = with_corruption_at_stage(sheet, resonance, stage=2)

        char_res = CharacterResonance.objects.get(
            character_sheet=sheet,
            resonance=resonance,
        )
        initial = char_res.corruption_current
        self.assertGreater(initial, 0)

        # Decay more than current — should clamp at 0
        decay_condition_severity(instance, amount=initial + 100)

        char_res.refresh_from_db()
        self.assertEqual(char_res.corruption_current, 0)

    def test_decay_does_not_touch_corruption_lifetime(self) -> None:
        """corruption_lifetime is monotonic — decay never decrements it."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        instance = with_corruption_at_stage(sheet, resonance, stage=2)

        char_res = CharacterResonance.objects.get(
            character_sheet=sheet,
            resonance=resonance,
        )
        lifetime_before = char_res.corruption_lifetime
        self.assertGreater(lifetime_before, 0)

        decay_condition_severity(instance, amount=10)

        char_res.refresh_from_db()
        self.assertEqual(char_res.corruption_lifetime, lifetime_before)

    def test_decay_for_non_corruption_condition_does_not_touch_char_resonance(self) -> None:
        """Decay on a non-Corruption condition (corruption_resonance=None on
        template) should not create or modify any CharacterResonance row."""
        # Build a vanilla (non-Corruption) condition instance
        template = ConditionTemplateFactory()  # corruption_resonance=None by default
        self.assertIsNone(template.corruption_resonance)

        character = CharacterFactory()
        stage = ConditionStageFactory(condition=template, severity_threshold=1)
        instance = ConditionInstanceFactory(
            target=character,
            condition=template,
            current_stage=stage,
            severity=50,
        )

        resonance_count_before = CharacterResonance.objects.count()

        decay_condition_severity(instance, amount=10)

        self.assertEqual(CharacterResonance.objects.count(), resonance_count_before)

    def test_no_infinite_recursion(self) -> None:
        """reduce_corruption with _from_decay=True must not call decay_condition_severity
        again — this test will hang or hit RecursionError if the guard is missing."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        instance = with_corruption_at_stage(sheet, resonance, stage=2)

        # This should complete without recursion error
        decay_condition_severity(instance, amount=5)
