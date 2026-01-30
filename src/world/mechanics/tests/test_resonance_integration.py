"""Tests for distinction resonance integration with CharacterResonanceTotal."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.magic.factories import ResonanceModifierTypeFactory
from world.magic.models import CharacterResonanceTotal
from world.mechanics.factories import ModifierTypeFactory
from world.mechanics.services import (
    create_distinction_modifiers,
    delete_distinction_modifiers,
    update_distinction_rank,
)


class DistinctionResonanceIntegrationTest(TestCase):
    """Tests for distinction effects that target resonances."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character_sheet = CharacterSheetFactory()
        cls.character = cls.character_sheet.character

        # Create a resonance ModifierType
        cls.serenity = ResonanceModifierTypeFactory(name="Serenity")

        # Create a non-resonance ModifierType for comparison
        cls.allure = ModifierTypeFactory(name="Allure")

    def test_create_distinction_updates_resonance_total(self):
        """Granting a distinction with resonance effect updates CharacterResonanceTotal."""
        # Create a distinction with a resonance effect
        patient = DistinctionFactory(name="Patient", max_rank=3)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity,
            value_per_rank=10,
        )

        # Grant distinction at rank 1
        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(char_dist)

        # Check resonance total was created/updated
        total = CharacterResonanceTotal.objects.get(
            character=self.character_sheet,
            resonance=self.serenity,
        )
        self.assertEqual(total.total, 10)  # 10 * rank 1

    def test_create_distinction_higher_rank_updates_resonance_total(self):
        """Distinction at higher rank gives proportionally higher resonance total."""
        patient = DistinctionFactory(name="Patient2", max_rank=3)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity,
            value_per_rank=10,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=3,
        )
        create_distinction_modifiers(char_dist)

        total = CharacterResonanceTotal.objects.get(
            character=self.character_sheet,
            resonance=self.serenity,
        )
        self.assertEqual(total.total, 30)  # 10 * rank 3

    def test_delete_distinction_subtracts_resonance_total(self):
        """Removing a distinction subtracts from CharacterResonanceTotal."""
        # Setup: grant and create modifiers
        patient = DistinctionFactory(name="Patient3", max_rank=3)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity,
            value_per_rank=10,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(char_dist)

        # Verify initial total
        total = CharacterResonanceTotal.objects.get(
            character=self.character_sheet,
            resonance=self.serenity,
        )
        self.assertEqual(total.total, 10)
        pk = total.pk

        # Delete
        delete_distinction_modifiers(char_dist)
        char_dist.delete()

        # Check total is now 0
        total = CharacterResonanceTotal.objects.get(pk=pk)
        self.assertEqual(total.total, 0)

    def test_update_rank_adjusts_resonance_total(self):
        """Updating distinction rank adjusts CharacterResonanceTotal by the difference."""
        patient = DistinctionFactory(name="Patient4", max_rank=5)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity,
            value_per_rank=10,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(char_dist)

        # Initial total
        total = CharacterResonanceTotal.objects.get(
            character=self.character_sheet,
            resonance=self.serenity,
        )
        self.assertEqual(total.total, 10)

        # Update rank
        char_dist.rank = 3
        char_dist.save()
        update_distinction_rank(char_dist)

        # New total should be 30
        total.refresh_from_db()
        self.assertEqual(total.total, 30)

    def test_update_rank_decrease_adjusts_resonance_total(self):
        """Decreasing distinction rank subtracts from CharacterResonanceTotal."""
        patient = DistinctionFactory(name="Patient5", max_rank=5)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity,
            value_per_rank=10,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=3,
        )
        create_distinction_modifiers(char_dist)

        # Initial total
        total = CharacterResonanceTotal.objects.get(
            character=self.character_sheet,
            resonance=self.serenity,
        )
        self.assertEqual(total.total, 30)

        # Decrease rank
        char_dist.rank = 1
        char_dist.save()
        update_distinction_rank(char_dist)

        # New total should be 10
        total.refresh_from_db()
        self.assertEqual(total.total, 10)

    def test_non_resonance_effect_does_not_create_resonance_total(self):
        """Effects targeting non-resonance types don't create CharacterResonanceTotal."""
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

        # No resonance total should be created for allure
        self.assertFalse(
            CharacterResonanceTotal.objects.filter(
                character=self.character_sheet,
                resonance=self.allure,
            ).exists()
        )

    def test_multiple_resonance_effects_update_separate_totals(self):
        """Distinction with multiple resonance effects updates each total."""
        # Create another resonance
        tranquility = ResonanceModifierTypeFactory(name="Tranquility")

        zen = DistinctionFactory(name="Zen Master", max_rank=3)
        DistinctionEffectFactory(
            distinction=zen,
            target=self.serenity,
            value_per_rank=5,
        )
        DistinctionEffectFactory(
            distinction=zen,
            target=tranquility,
            value_per_rank=8,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=zen,
            rank=2,
        )
        create_distinction_modifiers(char_dist)

        # Check both resonance totals
        serenity_total = CharacterResonanceTotal.objects.get(
            character=self.character_sheet,
            resonance=self.serenity,
        )
        self.assertEqual(serenity_total.total, 10)  # 5 * rank 2

        tranquility_total = CharacterResonanceTotal.objects.get(
            character=self.character_sheet,
            resonance=tranquility,
        )
        self.assertEqual(tranquility_total.total, 16)  # 8 * rank 2

    def test_multiple_distinctions_same_resonance_stack(self):
        """Multiple distinctions affecting same resonance stack correctly."""
        # First distinction
        patient = DistinctionFactory(name="Patient6")
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity,
            value_per_rank=10,
        )
        cd1 = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(cd1)

        # Second distinction
        calm = DistinctionFactory(name="Calm")
        DistinctionEffectFactory(
            distinction=calm,
            target=self.serenity,
            value_per_rank=5,
        )
        cd2 = CharacterDistinctionFactory(
            character=self.character,
            distinction=calm,
            rank=1,
        )
        create_distinction_modifiers(cd2)

        # Total should be sum of both
        total = CharacterResonanceTotal.objects.get(
            character=self.character_sheet,
            resonance=self.serenity,
        )
        self.assertEqual(total.total, 15)  # 10 + 5

    def test_delete_one_distinction_leaves_other_resonance_total(self):
        """Deleting one distinction preserves other's contribution to resonance total."""
        # First distinction
        patient = DistinctionFactory(name="Patient7")
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity,
            value_per_rank=10,
        )
        cd1 = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(cd1)

        # Second distinction
        calm = DistinctionFactory(name="Calm2")
        DistinctionEffectFactory(
            distinction=calm,
            target=self.serenity,
            value_per_rank=5,
        )
        cd2 = CharacterDistinctionFactory(
            character=self.character,
            distinction=calm,
            rank=1,
        )
        create_distinction_modifiers(cd2)

        # Delete first distinction
        delete_distinction_modifiers(cd1)
        cd1.delete()

        # Total should now be just the second distinction's contribution
        total = CharacterResonanceTotal.objects.get(
            character=self.character_sheet,
            resonance=self.serenity,
        )
        self.assertEqual(total.total, 5)

    def test_scaling_values_used_for_resonance_total(self):
        """Custom scaling_values are used correctly for resonance totals."""
        patient = DistinctionFactory(name="Patient8", max_rank=3)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity,
            scaling_values=[5, 15, 30],  # Non-linear scaling
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character,
            distinction=patient,
            rank=2,
        )
        create_distinction_modifiers(char_dist)

        total = CharacterResonanceTotal.objects.get(
            character=self.character_sheet,
            resonance=self.serenity,
        )
        self.assertEqual(total.total, 15)  # scaling_values[1] for rank 2
