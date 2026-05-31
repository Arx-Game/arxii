"""Tests for power-scoped modifiers feeding _derive_power (#634)."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import ResonanceFactory, TechniqueFactory
from world.magic.services.techniques import _derive_power
from world.mechanics.constants import POWER_CATEGORY_NAME
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
)


class PowerDerivationTests(TestCase):
    """A power-scoped CharacterModifier raises derived power, additively, floored at 0."""

    def setUp(self):
        self.category = ModifierCategoryFactory(name=POWER_CATEGORY_NAME)
        self.global_target = ModifierTargetFactory(
            category=self.category, name="power", target_resonance=None
        )
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.technique = TechniqueFactory()

    def _add_power(self, target, value):
        source = DistinctionModifierSourceFactory()
        CharacterModifierFactory(character=self.sheet, target=target, value=value, source=source)

    def test_global_power_modifier_raises_derived_power(self):
        self._add_power(self.global_target, 5)
        result = _derive_power(
            channeled_intensity=7, technique=self.technique, character=self.character
        )
        self.assertEqual(result, 12)

    def test_resonance_scoped_power_applies_on_matching_technique(self):
        fire = ResonanceFactory(name="Fire")
        self.technique.gift.resonances.add(fire)
        fire_target = ModifierTargetFactory(
            category=self.category, name="power_fire", target_resonance=fire
        )
        self._add_power(fire_target, 4)
        result = _derive_power(
            channeled_intensity=3, technique=self.technique, character=self.character
        )
        self.assertEqual(result, 7)

    def test_resonance_scoped_power_skipped_on_non_matching_technique(self):
        fire = ResonanceFactory(name="Fire")  # NOT added to the technique's gift
        fire_target = ModifierTargetFactory(
            category=self.category, name="power_fire", target_resonance=fire
        )
        self._add_power(fire_target, 4)
        result = _derive_power(
            channeled_intensity=3, technique=self.technique, character=self.character
        )
        self.assertEqual(result, 3)

    def test_global_power_applies_regardless_of_resonance(self):
        fire = ResonanceFactory(name="Fire")
        self.technique.gift.resonances.add(fire)
        self._add_power(self.global_target, 2)
        result = _derive_power(
            channeled_intensity=3, technique=self.technique, character=self.character
        )
        self.assertEqual(result, 5)

    def test_none_character_returns_channeled_intensity(self):
        self._add_power(self.global_target, 5)
        self.assertEqual(
            _derive_power(channeled_intensity=4, technique=self.technique, character=None),
            4,
        )

    def test_character_without_sheet_returns_channeled_intensity(self):
        bare = CharacterFactory()  # no CharacterSheet created for this character
        self._add_power(self.global_target, 5)
        self.assertEqual(
            _derive_power(channeled_intensity=4, technique=self.technique, character=bare),
            4,
        )

    def test_none_technique_still_applies_global_power(self):
        self._add_power(self.global_target, 6)
        self.assertEqual(
            _derive_power(channeled_intensity=1, technique=None, character=self.character),
            7,
        )

    def test_negative_power_modifier_floors_at_zero(self):
        self._add_power(self.global_target, -100)
        self.assertEqual(
            _derive_power(
                channeled_intensity=5, technique=self.technique, character=self.character
            ),
            0,
        )

    def test_power_modifier_does_not_change_channeled_intensity(self):
        self._add_power(self.global_target, 5)
        channeled = 7
        power = _derive_power(
            channeled_intensity=channeled, technique=self.technique, character=self.character
        )
        # Power rose; the channeled-intensity input (which drives anima/mishap/Soulfray) did not.
        self.assertEqual(power, 12)
        self.assertEqual(channeled, 7)


class PowerFactoryDefaultsTests(TestCase):
    """The power default factories are idempotent and feed _derive_power."""

    def test_factories_are_idempotent(self):
        from world.mechanics.factories import GlobalPowerTargetFactory

        first = GlobalPowerTargetFactory()
        second = GlobalPowerTargetFactory()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.category.name, "power")
        self.assertIsNone(first.target_resonance_id)
