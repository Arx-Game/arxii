"""Tests for MissionOptionRoute.consequence (Phase 3, Task 3.0).

Phase 2 under-modeled the per-route authored consequence. A route may now
carry an authored ``checks.Consequence`` (applied when its outcome tier is
rolled) or omit it (pure routing / no effect).
"""

from django.test import TestCase

from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.traits.factories import CheckOutcomeFactory


class MissionOptionRouteConsequenceTests(TestCase):
    """A route can carry an authored consequence or leave it null."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="route-conseq-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.node_a = MissionNodeFactory(template=cls.template, key="a")
        cls.success = CheckOutcomeFactory(name="Success")
        cls.sneak = CheckTypeFactory(name="SneakConseq")
        cls.option = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.sneak,
        )

    def test_route_can_carry_a_consequence(self) -> None:
        consequence = ConsequenceFactory(outcome_tier=self.success)
        route = MissionOptionRouteFactory(
            option=self.option,
            outcome_tier=self.success,
            target_node=self.node_a,
            consequence=consequence,
        )
        route.refresh_from_db()
        self.assertEqual(route.consequence, consequence)

    def test_route_consequence_defaults_to_null(self) -> None:
        route = MissionOptionRouteFactory(
            option=self.option,
            outcome_tier=self.success,
            target_node=self.node_a,
        )
        self.assertIsNone(route.consequence)
