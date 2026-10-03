"""The bearer of an allegiance condition never rolls to shake it off (#4091, Decision 15)."""

from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.conditions.constants import Allegiance, BreakFreeMode
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.services import attempt_break_free


class AllegianceBreakFreeTests(TestCase):
    def test_not_attempted(self):
        charm = ConditionTemplateFactory(
            name="Charm BF",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=CheckTypeFactory(name="BF check"),
            break_free_mode=BreakFreeMode.PERIODIC,
        )
        instance = ConditionInstanceFactory(condition=charm, is_aware=True)
        result = attempt_break_free(instance, in_combat_tick=True)
        self.assertFalse(result.attempted)
        self.assertFalse(result.broke_free)
