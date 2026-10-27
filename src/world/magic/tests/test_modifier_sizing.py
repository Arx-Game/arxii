"""A technique buff's level and size (#4594).

The cast's power and outcome resolve a level from rows; a sized applied-condition row
stamps that level and its size on the condition it lands; the condition's check
modifiers then read the value table, never the bearer's level. The admin size check
warns when a size doesn't fit how the technique spends its power.
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierLane, ModifierSize
from world.checks.factories import CheckTypeFactory
from world.checks.modifier_models import ModifierValue
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import get_check_modifier
from world.magic.factories import (
    TechniqueAppliedConditionFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
    TechniqueMoraleEffectFactory,
)
from world.magic.models.modifier_level import CastOutcomeLevelShift, CastPowerLevel
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services.condition_application import apply_technique_conditions
from world.magic.services.modifier_sizing import (
    CastLevelTable,
    _technique_effect_count,
    applied_condition_size_warnings,
    load_cast_level_table,
)
from world.magic.services.technique_effects import invalidate_technique_payload_caches
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.traits.factories import StatTraitFactory


class CastLevelTableTests(SimpleTestCase):
    TABLE = CastLevelTable(power_levels=((0, 1), (16, 6), (30, 11)), outcome_shifts={2: 2})

    def test_power_picks_the_highest_row_at_or_below_it(self) -> None:
        self.assertEqual(self.TABLE.level_for(effective_power=20, success_level=1), 6)
        self.assertEqual(self.TABLE.level_for(effective_power=30, success_level=1), 11)

    def test_a_critical_success_shifts_the_level(self) -> None:
        self.assertEqual(self.TABLE.level_for(effective_power=20, success_level=2), 8)

    def test_a_weak_cast_with_no_row_has_no_level(self) -> None:
        table = CastLevelTable(power_levels=((10, 3),))

        self.assertIsNone(table.level_for(effective_power=5, success_level=1))

    def test_a_shift_never_takes_the_level_below_one(self) -> None:
        table = CastLevelTable(power_levels=((0, 1),), outcome_shifts={0: -3})

        self.assertEqual(table.level_for(effective_power=0, success_level=0), 1)


class SizedBuffLandsTests(TestCase):
    """A cast stamps the level and size, and the check reads the value table."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_type = CheckTypeFactory(name="Sized buff check")
        cls.condition = ConditionTemplateFactory(name="Sharpened")
        ConditionCheckModifierFactory(
            condition=cls.condition, check_type=cls.check_type, modifier_value=5
        )
        cls.technique = TechniqueFactory(damage_profile=False)
        cls.row = TechniqueAppliedConditionFactory(
            technique=cls.technique,
            condition=cls.condition,
            target_kind=ConditionTargetKind.ALLY,
            modifier_size=ModifierSize.LARGE,
        )
        CastPowerLevel.objects.create(min_power=0, level=1)
        CastPowerLevel.objects.create(min_power=16, level=6)
        CastOutcomeLevelShift.objects.create(success_level=2, level_shift=2)
        for level, value in ((1, 3), (6, 10), (8, 13)):
            ModifierValue.objects.create(
                lane=ModifierLane.CHECK, level=level, size=ModifierSize.LARGE, value=value
            )

    def setUp(self) -> None:
        self.caster = CharacterSheetFactory().character
        self.ally_sheet = CharacterSheetFactory()

    def cast(self, *, power: int, success_level: int = 1) -> ConditionInstance:
        apply_technique_conditions(
            technique=self.technique,
            success_level=success_level,
            eff_intensity=power,
            targets_by_kind={ConditionTargetKind.ALLY: [self.ally_sheet.character]},
            source_character=self.caster,
        )
        return ConditionInstance.objects.get(
            target=self.ally_sheet.character, condition=self.condition
        )

    def test_the_cast_stamps_its_level_and_the_rows_size(self) -> None:
        instance = self.cast(power=20)

        self.assertEqual(instance.modifier_level, 6)
        self.assertEqual(instance.modifier_size, ModifierSize.LARGE)

    def test_the_check_reads_the_value_table_not_the_flat_value(self) -> None:
        self.cast(power=20)

        result = get_check_modifier(self.ally_sheet, self.check_type)

        self.assertEqual(result.total_modifier, 10)

    def test_a_critical_success_casts_a_higher_level_buff(self) -> None:
        instance = self.cast(power=20, success_level=2)

        self.assertEqual(instance.modifier_level, 8)
        self.assertEqual(get_check_modifier(self.ally_sheet, self.check_type).total_modifier, 13)

    def test_a_debuff_keeps_its_minus_sign(self) -> None:
        cursed = ConditionTemplateFactory(name="Dulled")
        ConditionCheckModifierFactory(
            condition=cursed, check_type=self.check_type, modifier_value=-5
        )
        TechniqueAppliedConditionFactory(
            technique=self.technique,
            condition=cursed,
            target_kind=ConditionTargetKind.ALLY,
            modifier_size=ModifierSize.LARGE,
        )
        invalidate_technique_payload_caches(self.technique)

        self.cast(power=20)

        # +10 from Sharpened, -10 from Dulled.
        self.assertEqual(get_check_modifier(self.ally_sheet, self.check_type).total_modifier, 0)

    def test_an_unsized_row_keeps_the_flat_value(self) -> None:
        self.row.modifier_size = None
        self.row.save()
        try:
            instance = self.cast(power=20)
            self.assertIsNone(instance.modifier_level)
            self.assertEqual(get_check_modifier(self.ally_sheet, self.check_type).total_modifier, 5)
        finally:
            self.row.modifier_size = ModifierSize.LARGE
            self.row.save()

    def test_a_level_below_every_value_row_keeps_the_flat_value(self) -> None:
        ModifierValue.objects.filter(level=1).delete()

        self.cast(power=0)

        self.assertEqual(get_check_modifier(self.ally_sheet, self.check_type).total_modifier, 5)

    def test_the_level_table_loads_in_two_queries(self) -> None:
        with self.assertNumQueries(2):
            table = load_cast_level_table()

        self.assertEqual(table.level_for(effective_power=16, success_level=1), 6)


class SizeCheckTests(TestCase):
    """The admin size check (#4551 section 5.3, item 4)."""

    @classmethod
    def setUpTestData(cls) -> None:
        check_type = CheckTypeFactory(name="Size check")
        cls.buff = ConditionTemplateFactory(name="Steadied")
        ConditionCheckModifierFactory(condition=cls.buff, check_type=check_type, modifier_value=4)

    def technique_with(self, *, size: int, damage: bool, narrow: bool = False):
        technique = TechniqueFactory(name="Steadying Strike", damage_profile=False)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=self.buff,
            target_kind=ConditionTargetKind.ALLY,
            modifier_size=size,
            narrow_use=narrow,
        )
        if damage:
            TechniqueDamageProfileFactory(technique=technique)
        invalidate_technique_payload_caches(technique)
        return technique

    def test_a_morale_row_counts_as_one_effect(self) -> None:
        technique = self.technique_with(size=ModifierSize.LARGE, damage=False)
        self.assertEqual(_technique_effect_count(technique), 1)

        TechniqueMoraleEffectFactory(technique=technique, base_morale=20)
        invalidate_technique_payload_caches(technique)

        self.assertEqual(_technique_effect_count(technique), 2)

    def test_a_two_effect_technique_sized_large_warns(self) -> None:
        technique = self.technique_with(size=ModifierSize.LARGE, damage=True)

        self.assertEqual(
            applied_condition_size_warnings(technique),
            [
                "Steadied is sized Large, but Steadying Strike does 1 other thing as well, "
                "so this buff shares the cast's power: at most Moderate."
            ],
        )

    def test_narrow_use_pays_for_one_step(self) -> None:
        technique = self.technique_with(size=ModifierSize.LARGE, damage=True, narrow=True)

        self.assertEqual(applied_condition_size_warnings(technique), [])

    def test_a_buff_only_technique_sized_large_is_quiet(self) -> None:
        technique = self.technique_with(size=ModifierSize.LARGE, damage=False)

        self.assertEqual(applied_condition_size_warnings(technique), [])

    def test_a_buff_only_technique_sized_small_warns(self) -> None:
        technique = self.technique_with(size=ModifierSize.MINOR, damage=False)

        self.assertEqual(
            applied_condition_size_warnings(technique),
            [
                "Steadied is sized Minor, but it is everything Steadying Strike does, "
                "so it gets the whole power budget: Large."
            ],
        )

    def test_a_sized_condition_that_changes_no_check_warns(self) -> None:
        technique = TechniqueFactory(name="Empty Gesture", damage_profile=False)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Hollow"),
            target_kind=ConditionTargetKind.ALLY,
            modifier_size=ModifierSize.LARGE,
        )
        invalidate_technique_payload_caches(technique)

        self.assertEqual(
            applied_condition_size_warnings(technique),
            [
                "Hollow is sized Large, but it changes no check or stat, so its size has "
                "nothing to act on yet."
            ],
        )

    def test_a_sized_condition_that_changes_a_stat_does_not_warn(self) -> None:
        """#4726: a stat buff is valued from the stat lane, so its size acts."""
        technique = TechniqueFactory(name="Ox Strength", damage_profile=False)
        condition = ConditionTemplateFactory(name="Ox Strength")
        ConditionModifierEffectFactory(
            condition=condition,
            modifier_target=ModifierTargetFactory(
                name="strength_4726",
                category=ModifierCategoryFactory(name="stat"),
                target_trait=StatTraitFactory(name="strength_4726"),
            ),
            value=10,
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=ConditionTargetKind.ALLY,
            modifier_size=ModifierSize.LARGE,
        )
        invalidate_technique_payload_caches(technique)

        self.assertEqual(applied_condition_size_warnings(technique), [])

    def test_paramount_cannot_be_authored(self) -> None:
        row = TechniqueAppliedConditionFactory.build(
            technique=TechniqueFactory(damage_profile=False),
            condition=self.buff,
            modifier_size=ModifierSize.PARAMOUNT,
        )

        with self.assertRaises(ValidationError):
            row.clean()
