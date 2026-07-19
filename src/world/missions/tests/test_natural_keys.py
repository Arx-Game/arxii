"""Natural-key round-trip tests for the mission-authoring graph (#2470)."""

from __future__ import annotations

from django.test import TestCase

from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionOptionRoute
from world.traits.factories import CheckOutcomeFactory


class MissionOptionRouteNaturalKeyTests(TestCase):
    """MissionOptionRoute.NaturalKeyConfig handles a nullable outcome_tier (#2470)."""

    def test_branch_route_null_tier_round_trips(self) -> None:
        template = MissionTemplateFactory(name="NK Branch Route Template")
        node = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(node=node, key="branch-option")
        route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)

        key = route.natural_key()
        fetched = MissionOptionRoute.objects.get_by_natural_key(*key)
        assert fetched.pk == route.pk

    def test_check_route_non_null_tier_round_trips(self) -> None:
        template = MissionTemplateFactory(name="NK Check Route Template")
        node = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(node=node, key="check-option")
        tier = CheckOutcomeFactory(name="NKSuccess", success_level=2)
        route = MissionOptionRouteFactory(option=option, outcome_tier=tier, target_node=None)

        key = route.natural_key()
        fetched = MissionOptionRoute.objects.get_by_natural_key(*key)
        assert fetched.pk == route.pk
