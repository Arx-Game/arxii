"""Tests for travel services (#1855)."""

import math
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from world.mechanics.models import ModifierTarget
from world.travel.constants import TravelMode
from world.travel.factories import TravelHubFactory, TravelRouteFactory
from world.travel.services import (
    compute_ap_cost,
    compute_travel_time,
    find_overworld_route,
)


class FindOverworldRouteTests(TestCase):
    def setUp(self):
        self.hub_a = TravelHubFactory(name="Hub A")
        self.hub_b = TravelHubFactory(name="Hub B")
        self.hub_c = TravelHubFactory(name="Hub C")

    def test_direct_route(self):
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            distance=100,
            travel_mode=TravelMode.LAND,
        )
        route = find_overworld_route(self.hub_a, self.hub_b, TravelMode.LAND)
        self.assertIsNotNone(route)
        self.assertEqual(len(route), 1)
        self.assertEqual(route[0].origin_hub, self.hub_a)
        self.assertEqual(route[0].destination_hub, self.hub_b)

    def test_multi_hop_route(self):
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_c,
            distance=50,
            travel_mode=TravelMode.LAND,
        )
        TravelRouteFactory(
            origin_hub=self.hub_c,
            destination_hub=self.hub_b,
            distance=50,
            travel_mode=TravelMode.LAND,
        )
        route = find_overworld_route(self.hub_a, self.hub_b, TravelMode.LAND)
        self.assertIsNotNone(route)
        self.assertEqual(len(route), 2)

    def test_no_route_found(self):
        route = find_overworld_route(self.hub_a, self.hub_b, TravelMode.SEA)
        self.assertIsNone(route)

    def test_mode_filtering(self):
        """A LAND route should not be found when filtering for SEA."""
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            distance=100,
            travel_mode=TravelMode.LAND,
        )
        route = find_overworld_route(self.hub_a, self.hub_b, TravelMode.SEA)
        self.assertIsNone(route)

    def test_bidirectional_route(self):
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            distance=100,
            travel_mode=TravelMode.LAND,
            is_bidirectional=True,
        )
        # Traveling B -> A on a bidirectional A -> B route
        route = find_overworld_route(self.hub_b, self.hub_a, TravelMode.LAND)
        self.assertIsNotNone(route)
        self.assertEqual(len(route), 1)

    @override_settings(OVERWORLD_MAX_HOPS=2)
    def test_hop_cap(self):
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_c,
            distance=50,
            travel_mode=TravelMode.LAND,
        )
        TravelRouteFactory(
            origin_hub=self.hub_c,
            destination_hub=self.hub_b,
            distance=50,
            travel_mode=TravelMode.LAND,
        )
        # 2 hops allowed, 2-hop route should work
        route = find_overworld_route(self.hub_a, self.hub_b, TravelMode.LAND)
        self.assertIsNotNone(route)
        self.assertEqual(len(route), 2)

    def test_same_origin_destination(self):
        route = find_overworld_route(self.hub_a, self.hub_a, TravelMode.LAND)
        self.assertEqual(route, [])

    def test_inactive_route_excluded(self):
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            distance=100,
            travel_mode=TravelMode.LAND,
            is_active=False,
        )
        route = find_overworld_route(self.hub_a, self.hub_b, TravelMode.LAND)
        self.assertIsNone(route)


class ComputeTravelTimeTests(TestCase):
    def setUp(self):
        self.route = MagicMock()
        self.route.distance = 100
        self.route.difficulty_modifier = 1.0
        self.method = MagicMock()
        self.method.base_speed = 10.0
        self.method.ship_type = None
        self.character_sheet = MagicMock()

    def test_basic_time(self):
        with (
            patch("world.mechanics.services.get_modifier_total", return_value=0),
            patch("world.mechanics.models.ModifierTarget.objects") as mock_mt,
        ):
            mock_mt.get.side_effect = ModifierTarget.DoesNotExist()
            time = compute_travel_time(self.route, self.method, self.character_sheet)
        self.assertAlmostEqual(time, 10.0)  # 100 / 10 = 10 IC hours

    def test_difficulty_modifier(self):
        with (
            patch("world.mechanics.services.get_modifier_total", return_value=0),
            patch("world.mechanics.models.ModifierTarget.objects") as mock_mt,
        ):
            mock_mt.get.side_effect = ModifierTarget.DoesNotExist()
            self.route.difficulty_modifier = 1.5
            time = compute_travel_time(self.route, self.method, self.character_sheet)
        self.assertAlmostEqual(time, 15.0)  # 10 * 1.5


class ComputeApCostTests(TestCase):
    @override_settings(AP_PER_IC_HOUR=2)
    def test_basic_cost(self):
        cost = compute_ap_cost(10.0)
        self.assertEqual(cost, 20)

    @override_settings(AP_PER_IC_HOUR=2)
    def test_rounds_up(self):
        cost = compute_ap_cost(5.1)
        self.assertEqual(cost, math.ceil(5.1 * 2))

    @override_settings(AP_PER_IC_HOUR=2)
    def test_minimum_one_ap(self):
        cost = compute_ap_cost(0.01)
        self.assertGreaterEqual(cost, 1)
