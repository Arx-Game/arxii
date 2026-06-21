from django.test import TestCase

from actions.constants import ActionTargetType
from world.magic.factories import TechniqueFactory


class TechniqueTargetTypeTests(TestCase):
    def test_defaults_to_single(self):
        tech = TechniqueFactory()
        self.assertEqual(tech.target_type, ActionTargetType.SINGLE)

    def test_target_type_authorable(self):
        tech = TechniqueFactory(target_type=ActionTargetType.AREA)
        self.assertEqual(tech.target_type, ActionTargetType.AREA)
