"""Tests for get_runtime_technique_stats() calculation pipeline."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import IntensityTierFactory, TechniqueFactory
from world.magic.services import get_runtime_technique_stats
from world.mechanics.constants import TECHNIQUE_STAT_CATEGORY_NAME
from world.mechanics.factories import (
    CharacterEngagementFactory,
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
)


class RuntimeStatsBaseTests(TestCase):
    """Base values and social safety bonus when no engagement exists."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=3)

    def test_no_character_returns_base_values(self) -> None:
        """When character is None, return raw technique stats."""
        result = get_runtime_technique_stats(self.technique, character=None)

        assert result.intensity == 5
        assert result.control == 3

    def test_character_without_engagement_gets_social_safety(self) -> None:
        """Unengaged character receives +10 social safety bonus to control."""
        sheet = CharacterSheetFactory()

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        assert result.intensity == 5
        assert result.control == 13  # 3 base + 10 social safety

    def test_character_without_sheet_still_gets_social_safety(self) -> None:
        """Character with no CharacterSheet still gets social safety bonus."""
        from evennia_extensions.factories import CharacterFactory

        character = CharacterFactory()

        result = get_runtime_technique_stats(self.technique, character=character)

        assert result.intensity == 5
        assert result.control == 13  # 3 base + 10 social safety


class RuntimeStatsIdentityModifierTests(TestCase):
    """CharacterModifier targeting technique_stat intensity/control."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=3)
        cls.category = ModifierCategoryFactory(name=TECHNIQUE_STAT_CATEGORY_NAME)
        cls.intensity_target = ModifierTargetFactory(category=cls.category, name="intensity")
        cls.control_target = ModifierTargetFactory(category=cls.category, name="control")

    def test_identity_intensity_modifier_applied(self) -> None:
        """CharacterModifier on intensity target adds to runtime intensity."""
        sheet = CharacterSheetFactory()
        source = DistinctionModifierSourceFactory()
        CharacterModifierFactory(
            character=sheet,
            source=source,
            target=self.intensity_target,
            value=3,
        )

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        assert result.intensity == 8  # 5 base + 3 identity
        # Control gets social safety but no identity modifier
        assert result.control == 13  # 3 base + 10 social safety

    def test_identity_control_modifier_applied(self) -> None:
        """CharacterModifier on control target adds to runtime control."""
        sheet = CharacterSheetFactory()
        source = DistinctionModifierSourceFactory()
        CharacterModifierFactory(
            character=sheet,
            source=source,
            target=self.control_target,
            value=5,
        )

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        assert result.intensity == 5  # base only
        assert result.control == 18  # 3 base + 5 identity + 10 social safety

    def test_both_identity_modifiers_applied(self) -> None:
        """Both intensity and control identity modifiers apply simultaneously."""
        sheet = CharacterSheetFactory()
        int_source = DistinctionModifierSourceFactory()
        ctl_source = DistinctionModifierSourceFactory()
        CharacterModifierFactory(
            character=sheet,
            source=int_source,
            target=self.intensity_target,
            value=2,
        )
        CharacterModifierFactory(
            character=sheet,
            source=ctl_source,
            target=self.control_target,
            value=4,
        )

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        assert result.intensity == 7  # 5 + 2
        assert result.control == 17  # 3 + 4 + 10 social safety

    def test_negative_identity_modifier(self) -> None:
        """Negative identity modifiers reduce stats."""
        sheet = CharacterSheetFactory()
        source = DistinctionModifierSourceFactory()
        CharacterModifierFactory(
            character=sheet,
            source=source,
            target=self.intensity_target,
            value=-2,
        )

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        assert result.intensity == 3  # 5 - 2


class RuntimeStatsEngagementTests(TestCase):
    """Engagement removes social safety and applies process modifiers."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=3)

    def test_engagement_removes_social_safety(self) -> None:
        """When engaged, social safety bonus does NOT apply."""
        sheet = CharacterSheetFactory()
        CharacterEngagementFactory(character=sheet.character)

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        assert result.intensity == 5
        assert result.control == 3  # base only, no +10

    def test_engagement_process_intensity_modifier(self) -> None:
        """Engagement intensity_modifier adds to runtime intensity."""
        sheet = CharacterSheetFactory()
        CharacterEngagementFactory(
            character=sheet.character,
            intensity_modifier=4,
        )

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        assert result.intensity == 9  # 5 + 4

    def test_engagement_process_control_modifier(self) -> None:
        """Engagement control_modifier adds to runtime control."""
        sheet = CharacterSheetFactory()
        CharacterEngagementFactory(
            character=sheet.character,
            control_modifier=7,
        )

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        assert result.control == 10  # 3 + 7 (no social safety)

    def test_engagement_both_process_modifiers(self) -> None:
        """Both process modifiers from engagement apply."""
        sheet = CharacterSheetFactory()
        CharacterEngagementFactory(
            character=sheet.character,
            intensity_modifier=3,
            control_modifier=2,
        )

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        assert result.intensity == 8  # 5 + 3
        assert result.control == 5  # 3 + 2 (no social safety)


class RuntimeStatsIntensityTierTests(TestCase):
    """IntensityTier.control_modifier integration."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=12, control=5)
        # Create tiers: Minor at 5, Moderate at 10, Major at 20
        IntensityTierFactory(name="Minor", threshold=5, control_modifier=0)
        IntensityTierFactory(name="Moderate", threshold=10, control_modifier=-2)
        IntensityTierFactory(name="Major", threshold=20, control_modifier=-5)

    def test_tier_control_modifier_applied(self) -> None:
        """IntensityTier control_modifier is added to runtime control."""
        sheet = CharacterSheetFactory()
        # Engaged so social safety doesn't interfere
        CharacterEngagementFactory(character=sheet.character)

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        # intensity=12 hits "Moderate" tier (threshold 10), control_modifier=-2
        assert result.intensity == 12
        assert result.control == 3  # 5 base + (-2) tier

    def test_no_tier_match_below_all_thresholds(self) -> None:
        """When intensity is below all thresholds, no tier modifier applies."""
        low_technique = TechniqueFactory(intensity=2, control=5)
        sheet = CharacterSheetFactory()
        CharacterEngagementFactory(character=sheet.character)

        result = get_runtime_technique_stats(low_technique, character=sheet.character)

        assert result.control == 5  # no tier modifier

    def test_highest_matching_tier_used(self) -> None:
        """The highest tier whose threshold <= intensity is used."""
        high_technique = TechniqueFactory(intensity=25, control=10)
        sheet = CharacterSheetFactory()
        CharacterEngagementFactory(character=sheet.character)

        result = get_runtime_technique_stats(high_technique, character=sheet.character)

        # intensity=25 hits "Major" tier (threshold 20), control_modifier=-5
        assert result.control == 5  # 10 + (-5)

    def test_tier_modifier_stacks_with_social_safety(self) -> None:
        """Tier modifier and social safety both apply when unengaged."""
        sheet = CharacterSheetFactory()
        # No engagement — social safety applies

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        # intensity=12, "Moderate" tier: control_modifier=-2
        # control = 5 base + 10 social safety + (-2) tier = 13
        assert result.control == 13

    def test_tier_modifier_with_identity_modifiers(self) -> None:
        """Tier is calculated from final runtime intensity including identity."""
        category = ModifierCategoryFactory(name=TECHNIQUE_STAT_CATEGORY_NAME)
        intensity_target = ModifierTargetFactory(category=category, name="intensity")
        # technique.intensity=12, identity adds 10 -> runtime=22 -> Major tier
        sheet = CharacterSheetFactory()
        CharacterEngagementFactory(character=sheet.character)
        source = DistinctionModifierSourceFactory()
        CharacterModifierFactory(
            character=sheet,
            source=source,
            target=intensity_target,
            value=10,
        )

        result = get_runtime_technique_stats(self.technique, character=sheet.character)

        assert result.intensity == 22  # 12 + 10
        # Major tier (threshold 20), control_modifier=-5
        assert result.control == 0  # 5 + (-5)
