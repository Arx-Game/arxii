"""Tests for power-scoped modifiers and power-term providers feeding _derive_power (#634, #637)."""

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


class LevelPowerTermTests(TestCase):
    """LevelPowerConfig drives how character and technique level feed into _derive_power (#637)."""

    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.technique = TechniqueFactory()

    def _set_character_level(self, level: int) -> None:
        from world.classes.factories import CharacterClassLevelFactory

        CharacterClassLevelFactory(character=self.character, level=level)
        self.sheet.invalidate_class_level_cache()

    def _make_config(self, *, char_bonus: int = 0, tech_bonus: int = 0):
        from world.magic.models import LevelPowerConfig

        return LevelPowerConfig.objects.create(
            pk=1, character_level_bonus=char_bonus, technique_level_bonus=tech_bonus
        )

    def test_character_level_raises_derived_power(self):
        self._make_config(char_bonus=2)
        self._set_character_level(3)
        result = _derive_power(
            channeled_intensity=5, technique=self.technique, character=self.character
        )
        self.assertEqual(result, 11)  # 5 intensity + 3 levels * 2

    def test_technique_level_raises_derived_power(self):
        self._make_config(tech_bonus=1)
        self.technique.level = 7
        self.technique.save()
        result = _derive_power(
            channeled_intensity=4, technique=self.technique, character=self.character
        )
        self.assertEqual(result, 11)  # 4 intensity + 7 technique levels * 1

    def test_both_bonuses_accumulate(self):
        self._make_config(char_bonus=1, tech_bonus=2)
        self._set_character_level(4)
        self.technique.level = 3
        self.technique.save()
        result = _derive_power(
            channeled_intensity=10, technique=self.technique, character=self.character
        )
        self.assertEqual(result, 20)  # 10 + 4*1 + 3*2

    def test_zero_bonuses_contribute_nothing(self):
        self._make_config(char_bonus=0, tech_bonus=0)
        self._set_character_level(10)
        result = _derive_power(
            channeled_intensity=5, technique=self.technique, character=self.character
        )
        self.assertEqual(result, 5)

    def test_no_config_row_contributes_nothing(self):
        self._set_character_level(5)
        result = _derive_power(
            channeled_intensity=5, technique=self.technique, character=self.character
        )
        self.assertEqual(result, 5)

    def test_character_with_no_class_level_contributes_nothing(self):
        self._make_config(char_bonus=5)
        # no CharacterClassLevel created → current_level == 0
        result = _derive_power(
            channeled_intensity=8, technique=self.technique, character=self.character
        )
        self.assertEqual(result, 8)

    def test_none_technique_still_applies_character_level(self):
        self._make_config(char_bonus=3)
        self._set_character_level(2)
        result = _derive_power(channeled_intensity=5, technique=None, character=self.character)
        self.assertEqual(result, 11)  # 5 + 2*3

    def test_level_term_does_not_affect_channeled_intensity(self):
        self._make_config(char_bonus=3)
        self._set_character_level(2)
        channeled = 7
        _derive_power(
            channeled_intensity=channeled, technique=self.technique, character=self.character
        )
        self.assertEqual(channeled, 7)


class ApplicableThreadsParameterTests(TestCase):
    """_derive_power accepts applicable_threads; thread provider is a stub returning 0 (#637)."""

    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.technique = TechniqueFactory()

    def test_empty_applicable_threads_does_not_change_power(self):
        result = _derive_power(
            channeled_intensity=5,
            technique=self.technique,
            character=self.character,
            applicable_threads=[],
        )
        self.assertEqual(result, 5)

    def test_applicable_threads_kwarg_accepted(self):
        from world.magic.factories import ThreadFactory
        from world.magic.services.power_terms import ApplicableThread

        resonance = ResonanceFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=resonance)
        threads = [ApplicableThread(thread=thread, pull_tier=1)]
        result = _derive_power(
            channeled_intensity=6,
            technique=self.technique,
            character=self.character,
            applicable_threads=threads,
        )
        # Stub returns 0 — power unchanged
        self.assertEqual(result, 6)
