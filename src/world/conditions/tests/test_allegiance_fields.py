"""ConditionTemplate allegiance fields and their validation (#4091)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.factories import ConsequencePoolFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionTemplateFactory


class AllegianceFieldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.check_type = CheckTypeFactory(name="Insight 4091")
        cls.pool = ConsequencePoolFactory()

    def test_allegiance_requires_break_check_type(self):
        template = ConditionTemplateFactory(sets_allegiance=Allegiance.ALLY_OF_CASTER)
        with self.assertRaises(ValidationError) as ctx:
            template.full_clean()
        self.assertIn("allegiance_break_check_type", ctx.exception.message_dict)

    def test_enemy_is_not_an_allegiance_effect(self):
        template = ConditionTemplateFactory(
            sets_allegiance=Allegiance.ENEMY, allegiance_break_check_type=self.check_type
        )
        with self.assertRaises(ValidationError) as ctx:
            template.full_clean()
        self.assertIn("sets_allegiance", ctx.exception.message_dict)

    def test_valid_charm_row(self):
        template = ConditionTemplateFactory(
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=self.check_type,
            settle_consequence_pool=self.pool,
        )
        template.full_clean()
