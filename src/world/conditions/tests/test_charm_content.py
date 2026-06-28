from django.test import TestCase

from world.conditions.charm_content import ensure_charm_content
from world.conditions.constants import CALM_CONDITION_NAME, CHARM_CONDITION_NAME
from world.conditions.models import ConditionCategory, ConditionTemplate


class EnsureCharmContentTest(TestCase):
    def test_creates_charm_category_with_alters_behavior(self):
        ensure_charm_content()
        cat = ConditionCategory.objects.get(name="Charm")
        self.assertTrue(cat.alters_behavior)

    def test_creates_charmed_and_calm_templates(self):
        ensure_charm_content()
        self.assertTrue(ConditionTemplate.objects.filter(name=CHARM_CONDITION_NAME).exists())
        self.assertTrue(ConditionTemplate.objects.filter(name=CALM_CONDITION_NAME).exists())

    def test_is_idempotent(self):
        ensure_charm_content()
        ensure_charm_content()
        self.assertEqual(ConditionTemplate.objects.filter(name=CHARM_CONDITION_NAME).count(), 1)
