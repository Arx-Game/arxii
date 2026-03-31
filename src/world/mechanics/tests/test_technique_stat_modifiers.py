"""Tests for technique stat modifier targets."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.constants import TECHNIQUE_STAT_CATEGORY_NAME
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
)
from world.mechanics.services import get_modifier_total


class TechniqueStatModifierTests(TestCase):
    """Verify CharacterModifiers can target technique stats."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.category = ModifierCategoryFactory(name=TECHNIQUE_STAT_CATEGORY_NAME)
        cls.intensity_target = ModifierTargetFactory(name="intensity", category=cls.category)
        cls.control_target = ModifierTargetFactory(name="control", category=cls.category)

    def test_intensity_modifier_stacks(self) -> None:
        source1 = DistinctionModifierSourceFactory()
        source2 = DistinctionModifierSourceFactory()
        CharacterModifierFactory(
            character=self.sheet,
            target=self.intensity_target,
            value=3,
            source=source1,
        )
        CharacterModifierFactory(
            character=self.sheet,
            target=self.intensity_target,
            value=5,
            source=source2,
        )
        assert get_modifier_total(self.sheet, self.intensity_target) == 8

    def test_control_modifier(self) -> None:
        source = DistinctionModifierSourceFactory()
        CharacterModifierFactory(
            character=self.sheet,
            target=self.control_target,
            value=4,
            source=source,
        )
        assert get_modifier_total(self.sheet, self.control_target) == 4

    def test_no_modifiers_returns_zero(self) -> None:
        assert get_modifier_total(self.sheet, self.intensity_target) == 0
