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

    def test_factory_category_alters_behavior(self):
        """Berserk is a behavior-altering condition — its category must carry
        alters_behavior=True so rage drives CharacterSheet.in_control=False
        (#1111 slice-4: revert blocked while raging)."""
        tpl = BerserkConditionTemplateFactory()
        self.assertTrue(
            tpl.category.alters_behavior,
            "Berserk's ConditionCategory must have alters_behavior=True.",
        )


class BerserkDesignationTests(TestCase):
    """Berserk is whatever ``FuryConfig.berserk_condition`` names (#4739)."""

    def test_unset_designation_finds_nothing(self):
        from world.magic.factories import FuryConfigFactory
        from world.magic.services.fury import berserk_condition_id, get_berserk_template

        FuryConfigFactory()
        self.assertIsNone(get_berserk_template())
        self.assertIsNone(berserk_condition_id())

    def test_factory_designates_and_a_rename_changes_nothing(self):
        from world.magic.services.fury import berserk_condition_id, get_berserk_template

        tpl = BerserkConditionTemplateFactory()
        tpl.name = "Red Haze"
        tpl.save(update_fields=["name"])
        self.assertEqual(get_berserk_template(), tpl)
        self.assertEqual(berserk_condition_id(), tpl.pk)

    def test_config_factory_applies_designation_to_an_existing_row(self):
        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.factories import FuryConfigFactory
        from world.magic.services.fury import get_berserk_template

        BerserkConditionTemplateFactory()
        other = ConditionTemplateFactory(name="Bloodfrenzy")
        FuryConfigFactory(berserk_condition=other)
        self.assertEqual(get_berserk_template(), other)
