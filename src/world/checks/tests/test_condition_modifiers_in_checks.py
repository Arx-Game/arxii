"""Condition stat-buffs fold into effective trait values and stat checks (#783).

A1 wired covenant-rite stat ModifierTargets to their Traits. A2 makes those
condition-sourced bonuses raise the *effective* trait value everywhere — both
the technique multiplier (already wired) and stat checks — by folding
get_condition_modifier_total into TraitHandler._get_stat_modifier.
"""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import (
    CheckCategoryFactory,
    CheckTypeFactory,
    CheckTypeTraitFactory,
)
from world.checks.services import perform_check
from world.conditions.factories import (
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import apply_condition
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.models import ModifierTarget
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    Trait,
    TraitCategory,
    TraitType,
)


class ConditionModifierInTraitValueTest(TestCase):
    """Test 1: an active condition's stat buff raises the effective trait value."""

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ModifierTarget.clear_trait_cache()

    def test_condition_stat_buff_raises_effective_trait_value(self):
        base = 30
        bonus = 15
        stat_name = "a2_trait_strength"

        sheet = CharacterSheetFactory()
        character = sheet.character

        strength = Trait.objects.create(
            name=stat_name,
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
        )
        CharacterTraitValue.objects.create(character=sheet, trait=strength, value=base)

        # ModifierTarget LINKED to the Trait (target_trait set), as A1 wires it.
        target = ModifierTargetFactory(name="a2_strength_target", target_trait=strength)

        condition = ConditionTemplateFactory(name="a2_strength_buff")
        ConditionModifierEffectFactory(condition=condition, modifier_target=target, value=bonus)
        apply_condition(target=character, condition=condition)

        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ModifierTarget.clear_trait_cache()

        self.assertEqual(character.traits.get_trait_value(stat_name), base + bonus)


class ConditionModifierInCheckTest(TestCase):
    """Test 2: end-to-end — the condition bonus raises a stat check's trait points."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        for rank_val, min_pts, name in [
            (0, 0, "A2None"),
            (1, 10, "A2Novice"),
            (2, 25, "A2Competent"),
            (3, 50, "A2Expert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val,
                defaults={"min_points": min_pts, "name": name},
            )
        # The character must have a CharacterSheet: _get_stat_modifier reads
        # self.character.sheet_data and returns 0 when it is absent, so a bare
        # CharacterFactory() (no sheet) would never see the condition fold-in.
        cls.character = CharacterSheetFactory().character
        cls.strength, _ = Trait.objects.get_or_create(
            name="a2_check_strength",
            defaults={
                "trait_type": TraitType.STAT,
                "category": TraitCategory.PHYSICAL,
            },
        )
        cls.category = CheckCategoryFactory(name="a2_check_combat")
        cls.check_type = CheckTypeFactory(name="a2_check_power_strike", category=cls.category)
        CheckTypeTraitFactory(
            check_type=cls.check_type,
            trait=cls.strength,
            weight=Decimal("1.0"),
        )

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ModifierTarget.clear_trait_cache()

    def test_condition_bonus_raises_check_trait_points(self):
        base = 30
        bonus = 40
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=base
        )

        result_base = perform_check(self.character, self.check_type, target_difficulty=0)

        target = ModifierTargetFactory(name="a2_check_strength_target", target_trait=self.strength)
        condition = ConditionTemplateFactory(name="a2_check_strength_buff")
        ConditionModifierEffectFactory(condition=condition, modifier_target=target, value=bonus)
        apply_condition(target=self.character, condition=condition)

        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ModifierTarget.clear_trait_cache()

        result_buffed = perform_check(self.character, self.check_type, target_difficulty=0)

        self.assertGreater(result_buffed.trait_points, result_base.trait_points)
