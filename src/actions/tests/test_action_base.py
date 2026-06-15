from django.test import SimpleTestCase

from actions.registry import get_action


class CostsTurnFlagTests(SimpleTestCase):
    def test_actions_default_to_not_costing_a_turn(self):
        start = get_action("start_round")
        assert start is not None
        assert start.costs_turn is False
