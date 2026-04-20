"""Tests for distinction resonance integration via CharacterModifier rows.

After Phase 2 of the resonance pivot, `CharacterResonanceTotal` was removed and
the aura recompute path now reads `CharacterModifier` rows whose target's
category is `resonance` directly. These tests assert on those rows (and on the
aura percentages they produce) instead of the deleted denormalized aggregate.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.magic.factories import AffinityFactory, ResonanceFactory
from world.magic.services import get_aura_percentages
from world.mechanics.constants import RESONANCE_CATEGORY_NAME
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import CharacterModifier
from world.mechanics.services import (
    create_distinction_modifiers,
    delete_distinction_modifiers,
    update_distinction_rank,
)


def _resonance_modifier_total(character_sheet, resonance):
    """Sum CharacterModifier values for a specific resonance via its target."""
    return sum(
        m.value
        for m in CharacterModifier.objects.filter(
            character=character_sheet,
            target__category__name=RESONANCE_CATEGORY_NAME,
            target__target_resonance=resonance,
        )
    )


class DistinctionResonanceIntegrationTest(TestCase):
    """Tests for distinction effects that target resonances."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character_sheet = CharacterSheetFactory()
        cls.character = cls.character_sheet.character

        # Affinity is needed so aura recompute can attribute resonance modifier
        # rows to the right affinity column.
        cls.abyssal = AffinityFactory(name="Abyssal")

        # Create a resonance with a linked ModifierTarget in the resonance category.
        resonance_category = ModifierCategoryFactory(name=RESONANCE_CATEGORY_NAME)
        cls.serenity = ResonanceFactory(name="Serenity", affinity=cls.abyssal)
        cls.serenity_target = ModifierTargetFactory(
            name="Serenity", category=resonance_category, target_resonance=cls.serenity
        )

        # Non-resonance ModifierTarget for comparison.
        cls.allure = ModifierTargetFactory(name="Allure")

    def test_create_distinction_creates_resonance_modifier(self):
        """Granting a distinction with a resonance effect creates a CharacterModifier."""
        patient = DistinctionFactory(name="Patient", max_rank=3)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity_target,
            value_per_rank=10,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(char_dist)

        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            10,  # 10 * rank 1
        )

    def test_create_distinction_higher_rank_scales_modifier(self):
        """Higher rank produces a proportionally larger modifier value."""
        patient = DistinctionFactory(name="Patient2", max_rank=3)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity_target,
            value_per_rank=10,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=3,
        )
        create_distinction_modifiers(char_dist)

        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            30,  # 10 * rank 3
        )

    def test_delete_distinction_removes_resonance_modifier(self):
        """Removing a distinction deletes its resonance CharacterModifier row."""
        patient = DistinctionFactory(name="Patient3", max_rank=3)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity_target,
            value_per_rank=10,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(char_dist)
        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            10,
        )

        delete_distinction_modifiers(char_dist)
        char_dist.delete()

        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            0,
        )

    def test_update_rank_adjusts_resonance_modifier(self):
        """Updating distinction rank updates the underlying CharacterModifier value."""
        patient = DistinctionFactory(name="Patient4", max_rank=5)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity_target,
            value_per_rank=10,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(char_dist)
        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            10,
        )

        char_dist.rank = 3
        char_dist.save()
        update_distinction_rank(char_dist)

        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            30,
        )

    def test_update_rank_decrease_adjusts_resonance_modifier(self):
        """Decreasing rank lowers the CharacterModifier value accordingly."""
        patient = DistinctionFactory(name="Patient5", max_rank=5)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity_target,
            value_per_rank=10,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=3,
        )
        create_distinction_modifiers(char_dist)
        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            30,
        )

        char_dist.rank = 1
        char_dist.save()
        update_distinction_rank(char_dist)

        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            10,
        )

    def test_non_resonance_effect_creates_no_resonance_modifier(self):
        """Effects targeting non-resonance targets create no resonance modifier rows."""
        charming = DistinctionFactory(name="Charming")
        DistinctionEffectFactory(
            distinction=charming,
            target=self.allure,
            value_per_rank=5,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=charming,
            rank=1,
        )
        create_distinction_modifiers(char_dist)

        self.assertFalse(
            CharacterModifier.objects.filter(
                character=self.character_sheet,
                target__category__name=RESONANCE_CATEGORY_NAME,
            ).exists()
        )

    def test_multiple_resonance_effects_create_separate_modifiers(self):
        """A distinction with multiple resonance effects creates per-target modifiers."""
        from world.mechanics.models import ModifierCategory

        resonance_category = ModifierCategory.objects.get(name=RESONANCE_CATEGORY_NAME)
        tranquility = ResonanceFactory(name="Tranquility", affinity=self.abyssal)
        tranquility_target = ModifierTargetFactory(
            name="Tranquility", category=resonance_category, target_resonance=tranquility
        )

        zen = DistinctionFactory(name="Zen Master", max_rank=3)
        DistinctionEffectFactory(
            distinction=zen,
            target=self.serenity_target,
            value_per_rank=5,
        )
        DistinctionEffectFactory(
            distinction=zen,
            target=tranquility_target,
            value_per_rank=8,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=zen,
            rank=2,
        )
        create_distinction_modifiers(char_dist)

        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            10,  # 5 * rank 2
        )
        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, tranquility),
            16,  # 8 * rank 2
        )

    def test_multiple_distinctions_same_resonance_stack(self):
        """Multiple distinctions affecting the same resonance produce additive total."""
        patient = DistinctionFactory(name="Patient6")
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity_target,
            value_per_rank=10,
        )
        cd1 = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(cd1)

        calm = DistinctionFactory(name="Calm")
        DistinctionEffectFactory(
            distinction=calm,
            target=self.serenity_target,
            value_per_rank=5,
        )
        cd2 = CharacterDistinctionFactory(
            character=self.character,
            distinction=calm,
            rank=1,
        )
        create_distinction_modifiers(cd2)

        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            15,  # 10 + 5
        )

    def test_delete_one_distinction_leaves_other_modifier(self):
        """Deleting one distinction preserves the other distinction's modifier."""
        patient = DistinctionFactory(name="Patient7")
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity_target,
            value_per_rank=10,
        )
        cd1 = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(cd1)

        calm = DistinctionFactory(name="Calm2")
        DistinctionEffectFactory(
            distinction=calm,
            target=self.serenity_target,
            value_per_rank=5,
        )
        cd2 = CharacterDistinctionFactory(
            character=self.character,
            distinction=calm,
            rank=1,
        )
        create_distinction_modifiers(cd2)

        delete_distinction_modifiers(cd1)
        cd1.delete()

        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            5,
        )

    def test_scaling_values_used_for_modifier(self):
        """Custom scaling_values populate the CharacterModifier value correctly."""
        patient = DistinctionFactory(name="Patient8", max_rank=3)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity_target,
            scaling_values=[5, 15, 30],  # Non-linear scaling
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=2,
        )
        create_distinction_modifiers(char_dist)

        self.assertEqual(
            _resonance_modifier_total(self.character_sheet, self.serenity),
            15,  # scaling_values[1] for rank 2
        )

    def test_resonance_modifier_feeds_aura_percentages(self):
        """End-to-end: a resonance modifier flows into get_aura_percentages output."""
        patient = DistinctionFactory(name="PatientAura", max_rank=3)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity_target,
            value_per_rank=100,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(char_dist)

        result = get_aura_percentages(self.character_sheet)
        # Serenity → Abyssal affinity, 100 value, no other contributions.
        self.assertEqual(result.abyssal, 100.0)
        self.assertEqual(result.celestial, 0.0)
        self.assertEqual(result.primal, 0.0)
