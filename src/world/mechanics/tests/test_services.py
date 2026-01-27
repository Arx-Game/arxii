"""Tests for mechanics service functions."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.mechanics.factories import ModifierTypeFactory
from world.mechanics.models import CharacterModifier
from world.mechanics.services import (
    create_distinction_modifiers,
    delete_distinction_modifiers,
    get_modifier_breakdown,
    get_modifier_total,
    update_distinction_rank,
)


class TestGetModifierBreakdown(TestCase):
    """Tests for get_modifier_breakdown function."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterSheetFactory()
        cls.allure = ModifierTypeFactory(name="Allure")

    def test_no_modifiers_returns_empty_breakdown(self):
        """Character with no modifiers returns zero total."""
        breakdown = get_modifier_breakdown(self.character, self.allure)

        assert breakdown.total == 0
        assert breakdown.sources == []
        assert breakdown.has_immunity is False
        assert breakdown.negatives_blocked == 0

    def test_single_modifier_simple_sum(self):
        """Single modifier returns its value as total."""
        distinction = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.allure,
            value_per_rank=5,
        )
        char_distinction = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=distinction,
            rank=2,
        )
        create_distinction_modifiers(char_distinction)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        assert breakdown.total == 10  # 5 * rank 2
        assert len(breakdown.sources) == 1
        assert breakdown.sources[0].source_name == "Attractive"
        assert breakdown.sources[0].base_value == 10

    def test_multiple_modifiers_sum(self):
        """Multiple modifiers are summed together."""
        # First distinction
        d1 = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(distinction=d1, target=self.allure, value_per_rank=5)
        cd1 = CharacterDistinctionFactory(
            character=self.character.character, distinction=d1, rank=1
        )
        create_distinction_modifiers(cd1)

        # Second distinction
        d2 = DistinctionFactory(name="Charming")
        DistinctionEffectFactory(distinction=d2, target=self.allure, value_per_rank=3)
        cd2 = CharacterDistinctionFactory(
            character=self.character.character, distinction=d2, rank=1
        )
        create_distinction_modifiers(cd2)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        assert breakdown.total == 8  # 5 + 3

    def test_amplification_applies_to_other_sources(self):
        """Amplifier adds bonus to other sources, not itself."""
        # Create Attractive with +10 Allure
        attractive = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(
            distinction=attractive,
            target=self.allure,
            value_per_rank=10,
        )

        # Create Cleans Up Well with +5 Allure and +2 amplification
        cleans_up = DistinctionFactory(name="Cleans Up Well")
        DistinctionEffectFactory(
            distinction=cleans_up,
            target=self.allure,
            value_per_rank=5,
            amplifies_sources_by=2,
        )

        # Grant both distinctions
        cd_attractive = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=attractive,
            rank=1,
        )
        cd_cleans = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=cleans_up,
            rank=1,
        )
        create_distinction_modifiers(cd_attractive)
        create_distinction_modifiers(cd_cleans)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        # Attractive: 10 + 2 (amplified) = 12
        # Cleans Up Well: 5 (no self-amplify)
        # Total: 17
        assert breakdown.total == 17

        # Check individual sources
        attractive_source = next(s for s in breakdown.sources if s.source_name == "Attractive")
        assert attractive_source.base_value == 10
        assert attractive_source.amplification == 2
        assert attractive_source.final_value == 12
        assert attractive_source.is_amplifier is False

        cleans_source = next(s for s in breakdown.sources if s.source_name == "Cleans Up Well")
        assert cleans_source.base_value == 5
        assert cleans_source.amplification == 0
        assert cleans_source.final_value == 5
        assert cleans_source.is_amplifier is True

    def test_multiple_amplifiers_stack(self):
        """Multiple amplifiers each add their bonus to other sources."""
        # Base distinction
        base = DistinctionFactory(name="Base")
        DistinctionEffectFactory(distinction=base, target=self.allure, value_per_rank=10)

        # Two amplifiers
        amp1 = DistinctionFactory(name="Amplifier1")
        DistinctionEffectFactory(
            distinction=amp1, target=self.allure, value_per_rank=5, amplifies_sources_by=2
        )

        amp2 = DistinctionFactory(name="Amplifier2")
        DistinctionEffectFactory(
            distinction=amp2, target=self.allure, value_per_rank=3, amplifies_sources_by=1
        )

        # Grant all
        cd_base = CharacterDistinctionFactory(
            character=self.character.character, distinction=base, rank=1
        )
        cd_amp1 = CharacterDistinctionFactory(
            character=self.character.character, distinction=amp1, rank=1
        )
        cd_amp2 = CharacterDistinctionFactory(
            character=self.character.character, distinction=amp2, rank=1
        )
        create_distinction_modifiers(cd_base)
        create_distinction_modifiers(cd_amp1)
        create_distinction_modifiers(cd_amp2)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        # Base: 10 + 2 + 1 = 13
        # Amp1: 5 + 1 = 6 (gets +1 from amp2)
        # Amp2: 3 + 2 = 5 (gets +2 from amp1)
        # Total: 13 + 6 + 5 = 24
        assert breakdown.total == 24

    def test_immunity_blocks_negative_modifiers(self):
        """Immunity prevents negative modifiers from counting."""
        # Create distinction with immunity
        spotless = DistinctionFactory(name="Somehow Always Spotless")
        DistinctionEffectFactory(
            distinction=spotless,
            target=self.allure,
            value_per_rank=5,
            grants_immunity_to_negative=True,
        )

        # Create a "debuff" distinction with negative value
        cursed = DistinctionFactory(name="Cursed Appearance")
        DistinctionEffectFactory(
            distinction=cursed,
            target=self.allure,
            value_per_rank=-3,
        )

        # Grant both
        cd_spotless = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=spotless,
            rank=1,
        )
        cd_cursed = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=cursed,
            rank=1,
        )
        create_distinction_modifiers(cd_spotless)
        create_distinction_modifiers(cd_cursed)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        # Spotless: 5
        # Cursed: -3 -> BLOCKED
        # Total: 5
        assert breakdown.total == 5
        assert breakdown.has_immunity is True
        assert breakdown.negatives_blocked == 1

        cursed_source = next(s for s in breakdown.sources if s.source_name == "Cursed Appearance")
        assert cursed_source.blocked_by_immunity is True

    def test_amplification_and_immunity_together(self):
        """Amplification and immunity work together correctly."""
        # Attractive: +10 Allure
        attractive = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(distinction=attractive, target=self.allure, value_per_rank=10)

        # Cleans Up Well: +5 Allure, +2 amplification
        cleans_up = DistinctionFactory(name="Cleans Up Well")
        DistinctionEffectFactory(
            distinction=cleans_up,
            target=self.allure,
            value_per_rank=5,
            amplifies_sources_by=2,
        )

        # Somehow Always Spotless: +5 Allure, immunity
        spotless = DistinctionFactory(name="Somehow Always Spotless")
        DistinctionEffectFactory(
            distinction=spotless,
            target=self.allure,
            value_per_rank=5,
            grants_immunity_to_negative=True,
        )

        # Grant all three
        cd_attractive = CharacterDistinctionFactory(
            character=self.character.character, distinction=attractive, rank=1
        )
        cd_cleans = CharacterDistinctionFactory(
            character=self.character.character, distinction=cleans_up, rank=1
        )
        cd_spotless = CharacterDistinctionFactory(
            character=self.character.character, distinction=spotless, rank=1
        )
        create_distinction_modifiers(cd_attractive)
        create_distinction_modifiers(cd_cleans)
        create_distinction_modifiers(cd_spotless)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        # Attractive: 10 + 2 = 12
        # Cleans Up Well: 5 (no self-amplify)
        # Somehow Always Spotless: 5 + 2 = 7
        # Total: 12 + 5 + 7 = 24
        assert breakdown.total == 24
        assert breakdown.has_immunity is True


class TestGetModifierTotal(TestCase):
    """Tests for get_modifier_total convenience function."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory()
        cls.allure = ModifierTypeFactory(name="Allure")

    def test_returns_total_from_breakdown(self):
        """get_modifier_total returns just the total value."""
        distinction = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.allure,
            value_per_rank=5,
        )
        cd = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=distinction,
            rank=2,
        )
        create_distinction_modifiers(cd)

        total = get_modifier_total(self.character, self.allure)
        assert total == 10


class TestDeleteDistinctionModifiers(TestCase):
    """Tests for delete_distinction_modifiers function."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory()
        cls.allure = ModifierTypeFactory(name="Allure")

    def test_deletes_all_modifiers_for_distinction(self):
        """Removes all CharacterModifier and ModifierSource records."""
        distinction = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(distinction=distinction, target=self.allure, value_per_rank=5)
        cd = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=distinction,
            rank=1,
        )
        create_distinction_modifiers(cd)

        # Verify modifiers exist
        assert CharacterModifier.objects.filter(character=self.character).count() == 1

        # Delete
        count = delete_distinction_modifiers(cd)

        assert count == 1
        assert CharacterModifier.objects.filter(character=self.character).count() == 0


class TestUpdateDistinctionRank(TestCase):
    """Tests for update_distinction_rank function."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory()
        cls.allure = ModifierTypeFactory(name="Allure")

    def test_updates_modifier_values_for_new_rank(self):
        """Recalculates modifier values when rank changes."""
        distinction = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(distinction=distinction, target=self.allure, value_per_rank=5)
        cd = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=distinction,
            rank=1,
        )
        create_distinction_modifiers(cd)

        # Initial value
        assert get_modifier_total(self.character, self.allure) == 5

        # Update rank
        cd.rank = 3
        cd.save()
        update_distinction_rank(cd)

        # New value
        assert get_modifier_total(self.character, self.allure) == 15
