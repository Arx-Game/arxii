from django.test import TestCase

from world.magic.constants import ParticipationRule
from world.magic.factories import RitualFactory


class RitualParticipationRuleTests(TestCase):
    def test_default_rule_is_single_actor(self):
        ritual = RitualFactory()
        self.assertEqual(ritual.participation_rule, ParticipationRule.SINGLE_ACTOR)

    def test_min_max_participants_default_null(self):
        ritual = RitualFactory()
        self.assertIsNone(ritual.min_participants)
        self.assertIsNone(ritual.max_participants)
