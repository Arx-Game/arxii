from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DamageTickTiming
from world.conditions.factories import (
    ConditionDamageOverTimeFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.services import _process_round_tick
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import tick_round_for_targets


class AcuteTickExcludesLongTermTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.target = cls.sheet.character
        cls.template = ConditionTemplateFactory(name="Poisoned-test")
        # Two distinct damage types: ConditionDamageOverTime has a unique
        # constraint on (condition, damage_type), so the acute and long-term
        # DoT rows on the same template must use different damage types.
        cls.acute_dtype = DamageTypeFactory(name="poison-acute")
        cls.long_term_dtype = DamageTypeFactory(name="poison-long-term")
        ConditionDamageOverTimeFactory(
            condition=cls.template,
            damage_type=cls.acute_dtype,
            base_damage=5,
            tick_timing=DamageTickTiming.END_OF_ROUND,
            is_long_term=False,
        )
        ConditionDamageOverTimeFactory(
            condition=cls.template,
            damage_type=cls.long_term_dtype,
            base_damage=99,
            tick_timing=DamageTickTiming.END_OF_ROUND,
            is_long_term=True,
        )
        ConditionInstanceFactory(target=cls.target, condition=cls.template)

    def test_acute_tick_ignores_long_term_rows(self):
        result = _process_round_tick(self.target, DamageTickTiming.END_OF_ROUND)
        amounts = [amt for _dt, amt in result.damage_dealt]
        self.assertIn(5, amounts)
        self.assertNotIn(99, amounts)


class AcuteDotDamagesHealthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.target = cls.sheet.character
        cls.vitals = CharacterVitalsFactory(character_sheet=cls.sheet, health=100, max_health=100)
        cls.dtype = DamageTypeFactory(name="poison-dmg")
        cls.template = ConditionTemplateFactory(name="Poisoned-dmg")
        ConditionDamageOverTimeFactory(
            condition=cls.template,
            damage_type=cls.dtype,
            base_damage=10,
            tick_timing=DamageTickTiming.END_OF_ROUND,
            is_long_term=False,
            scales_with_severity=False,
            scales_with_stacks=False,
        )
        ConditionInstanceFactory(target=cls.target, condition=cls.template)

    def test_end_tick_reduces_health_by_dot(self):
        tick_round_for_targets([self.target], timing="end")
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 90)


class EnsurePoisonContentTests(TestCase):
    def test_seeds_idempotently(self):
        from world.conditions.constants import (
            POISON_DAMAGE_TYPE_NAME,
            POISONED_CONDITION_NAME,
            SLOW_POISON_CONDITION_NAME,
        )
        from world.conditions.models import (
            ConditionDamageOverTime,
            ConditionTemplate,
            DamageType,
        )
        from world.conditions.services import ensure_poison_content

        ensure_poison_content()
        ensure_poison_content()  # must not duplicate

        self.assertEqual(DamageType.objects.filter(name=POISON_DAMAGE_TYPE_NAME).count(), 1)
        acute = ConditionTemplate.objects.get(name=POISONED_CONDITION_NAME)
        slow = ConditionTemplate.objects.get(name=SLOW_POISON_CONDITION_NAME)
        self.assertTrue(acute.has_progression)
        self.assertEqual(acute.stages.count(), 2)
        self.assertTrue(
            ConditionDamageOverTime.objects.filter(condition=acute, is_long_term=False).exists()
        )
        self.assertTrue(
            ConditionDamageOverTime.objects.filter(condition=slow, is_long_term=True).exists()
        )
