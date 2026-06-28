from django.test import TestCase

from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)


class EffectPaletteFieldsTests(TestCase):
    def test_defaults(self):
        cat = ConditionCategoryFactory()
        tmpl = ConditionTemplateFactory()
        inst = ConditionInstanceFactory()
        self.assertFalse(cat.grants_intangibility)
        self.assertEqual(tmpl.upkeep_anima_per_round, 0)
        self.assertEqual(tmpl.reactive_anima_cost, 0)
        self.assertIsNone(inst.absorb_remaining)

    def test_values_persist(self):
        cat = ConditionCategoryFactory(grants_intangibility=True)
        tmpl = ConditionTemplateFactory(upkeep_anima_per_round=2, reactive_anima_cost=3)
        inst = ConditionInstanceFactory(absorb_remaining=20)
        for obj in (cat, tmpl, inst):
            obj.refresh_from_db()
        self.assertTrue(cat.grants_intangibility)
        self.assertEqual(tmpl.upkeep_anima_per_round, 2)
        self.assertEqual(tmpl.reactive_anima_cost, 3)
        self.assertEqual(inst.absorb_remaining, 20)
