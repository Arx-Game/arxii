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
