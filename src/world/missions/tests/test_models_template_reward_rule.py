"""Tests for ``MissionTemplate.reward_group_rule`` (Phase 4, Task 4.0).

The field is the multi-participant payout-split *authoring knob* only;
the actual reward distribution-by-rule is Phase 5. Here we only assert the
field round-trips and defaults to ALL_EQUAL.
"""

from django.test import TestCase

from world.missions.constants import RewardGroupRule
from world.missions.factories import MissionTemplateFactory
from world.missions.models import MissionTemplate


class RewardGroupRuleFieldTests(TestCase):
    """Field default + round-trip across the three rules."""

    def test_default_is_all_equal(self) -> None:
        template = MissionTemplateFactory(name="rgr-default")
        template.refresh_from_db()
        self.assertEqual(template.reward_group_rule, RewardGroupRule.ALL_EQUAL)

    def test_round_trips_each_rule(self) -> None:
        for rule in (
            RewardGroupRule.ALL_EQUAL,
            RewardGroupRule.BY_ROLE,
            RewardGroupRule.BY_PARTICIPATION,
        ):
            template = MissionTemplateFactory(
                name=f"rgr-{rule}",
                reward_group_rule=rule,
            )
            reloaded = MissionTemplate.objects.get(pk=template.pk)
            self.assertEqual(reloaded.reward_group_rule, rule)
