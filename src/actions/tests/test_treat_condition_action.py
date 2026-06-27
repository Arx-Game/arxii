from django.test import TestCase

from actions.registry import get_action
from actions.types import TargetType


class TreatConditionActionRegistryTests(TestCase):
    def test_action_is_registered(self):
        action = get_action("treat_condition")
        self.assertIsNotNone(action)
        self.assertEqual(action.name, "Treat Condition")
        self.assertEqual(action.target_type, TargetType.SINGLE)
