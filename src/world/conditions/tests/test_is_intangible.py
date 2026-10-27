from django.test import TestCase

from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import is_intangible


class IsIntangibleTests(TestCase):
    def test_false_without_intangibility(self):
        inst = ConditionInstanceFactory()
        self.assertFalse(is_intangible(inst.target))

    def test_true_with_active_intangibility(self):
        cat = ConditionCategoryFactory(grants_intangibility=True)
        tmpl = ConditionTemplateFactory(category=cat)
        inst = ConditionInstanceFactory(condition=tmpl)
        self.assertTrue(is_intangible(inst.target))

    def test_false_when_suppressed(self):
        cat = ConditionCategoryFactory(grants_intangibility=True)
        tmpl = ConditionTemplateFactory(category=cat)
        inst = ConditionInstanceFactory(condition=tmpl, is_suppressed=True)
        self.assertFalse(is_intangible(inst.target))
