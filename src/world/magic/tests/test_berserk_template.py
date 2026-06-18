"""Tests for the Berserk ConditionTemplate factory (Task 7 / #567)."""

from django.test import TestCase

from world.conditions.models import ConditionTemplate
from world.magic.factories import BerserkConditionTemplateFactory


class BerserkTemplateTests(TestCase):
    def test_factory_creates_named_template(self):
        BerserkConditionTemplateFactory()
        self.assertIsNotNone(ConditionTemplate.get_by_name("Berserk"))

    def test_factory_has_rounds_duration(self):
        tpl = BerserkConditionTemplateFactory()
        from world.conditions.constants import DurationType

        self.assertEqual(tpl.default_duration_type, DurationType.ROUNDS)

    def test_factory_has_stage(self):
        BerserkConditionTemplateFactory()
        tpl = ConditionTemplate.get_by_name("Berserk")
        self.assertTrue(tpl.stages.exists(), "Berserk template must have at least one stage")

    def test_factory_is_idempotent(self):
        BerserkConditionTemplateFactory()
        BerserkConditionTemplateFactory()
        self.assertEqual(ConditionTemplate.objects.filter(name="Berserk").count(), 1)
