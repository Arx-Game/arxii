"""Tests for passive_mantle_crossing_bonuses — MANTLE crossing buff in equipment_walk_total (#1992).

Pipeline: build sheet + MANTLE-kind Thread + CrossingChoice (ConditionTemplate with
ConditionModifierEffect) -> call equipment_walk_total(sheet, target) -> assert the
crossing buff's ConditionModifierEffect value is included.

Always-on: the buff contributes even when the character is NOT wearing/holding the
mantle item (unlike FACET, which is wear-gated).
"""

from __future__ import annotations

from django.test import TestCase


class MantleCrossingBonusPipelineTests(TestCase):
    """Happy path: a MANTLE thread crossing choice contributes via equipment_walk_total."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import (
            ConditionModifierEffectFactory,
            ConditionTemplateFactory,
        )
        from world.items.factories import MantleFactory
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.magic.models.crossing import CrossingChoice, CrossingOption
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        cls.effect_value = 7

        # 1. Character + CharacterSheet
        cls.character_obj = CharacterFactory(db_key="MantleCrossingBonusChar")
        cls.sheet = CharacterSheetFactory(character=cls.character_obj, primary_persona=False)

        # 2. Resonance + ModifierTarget linked via target_resonance
        cls.resonance = ResonanceFactory()
        cls.resonance_category = ModifierCategoryFactory(name="resonance")
        cls.target = ModifierTargetFactory(
            name="MantleCrossingBonusTarget",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
        )

        # 3. Mantle + MANTLE-kind Thread
        cls.mantle = MantleFactory(name="MantleCrossingBonusMantle")
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            level=3,
            target_kind=TargetKind.MANTLE,
            target_mantle=cls.mantle,
            target_trait=None,
        )

        # 4. CrossingOption + CrossingChoice (the crossing buff)
        cls.condition_template = ConditionTemplateFactory()
        ConditionModifierEffectFactory(
            condition=cls.condition_template,
            modifier_target=cls.target,
            value=cls.effect_value,
        )
        cls.option = CrossingOption.objects.create(
            target_kind=TargetKind.MANTLE,
            resonance=cls.resonance,
            crossing_level=3,
            name="Mantle crossing buff",
            condition_template=cls.condition_template,
        )
        CrossingChoice.objects.create(
            thread=cls.thread,
            crossing_level=3,
            option=cls.option,
        )

    def test_crossing_bonus_in_equipment_walk_total(self) -> None:
        """equipment_walk_total includes the MANTLE crossing buff value."""
        from world.mechanics.services import equipment_walk_total

        self.character_obj.threads.invalidate()
        self.character_obj.equipped_items.invalidate()

        result = equipment_walk_total(self.sheet, self.target)
        self.assertEqual(result, self.effect_value)

    def test_crossing_bonus_always_on_without_equipment(self) -> None:
        """The crossing buff contributes even with no items equipped (always-on)."""
        from world.mechanics.services import equipment_walk_total

        self.character_obj.threads.invalidate()
        self.character_obj.equipped_items.invalidate()

        # No items equipped at all -- buff still contributes
        result = equipment_walk_total(self.sheet, self.target)
        self.assertEqual(result, self.effect_value)


class MantleCrossingBonusNoThreadTests(TestCase):
    """Negative path: no MANTLE thread -> 0 via equipment_walk_total."""

    def test_no_mantle_thread_returns_zero(self) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
        from world.mechanics.services import equipment_walk_total

        char = CharacterFactory(db_key="MantleCrossingNoThreadChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        resonance = ResonanceFactory()

        resonance_category = ModifierCategoryFactory(name="resonance")
        target = ModifierTargetFactory(
            name="MantleCrossingNoThreadTarget",
            category=resonance_category,
            target_resonance=resonance,
        )

        result = equipment_walk_total(sheet, target)
        self.assertEqual(result, 0)
