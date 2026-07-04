from django.test import TestCase

from world.conditions.models import ConditionCategory, ConditionTemplate
from world.seeds.perception_conditions import seed_perception_condition_content


class SeedPerceptionConditionsTests(TestCase):
    def test_seeds_concealed_category_and_template(self) -> None:
        seed_perception_condition_content()

        category = ConditionCategory.objects.get(name="Concealed")
        self.assertTrue(category.conceals_from_perception)
        self.assertFalse(category.alters_behavior)

        template = ConditionTemplate.objects.get(name="Concealed")
        self.assertEqual(template.category, category)

    def test_idempotent(self) -> None:
        seed_perception_condition_content()
        seed_perception_condition_content()

        self.assertEqual(ConditionCategory.objects.filter(name="Concealed").count(), 1)
        self.assertEqual(ConditionTemplate.objects.filter(name="Concealed").count(), 1)
