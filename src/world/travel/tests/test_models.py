"""Tests for travel models (#1855)."""

from django.test import TestCase

from world.travel.constants import TravelMode, VoyageStatus
from world.travel.models import (
    TravelHub,
    TravelMethod,
    TravelRoute,
    Voyage,
)


class TravelHubModelTests(TestCase):
    def test_str(self):
        hub = TravelHub(name="Port Meridian", description="")
        self.assertEqual(str(hub), "Port Meridian")

    def test_default_is_transit_stop(self):
        hub = TravelHub(name="Test Hub")
        self.assertTrue(hub.is_transit_stop)

    def test_default_is_active(self):
        hub = TravelHub(name="Test Hub")
        self.assertTrue(hub.is_active)


class TravelRouteModelTests(TestCase):
    def test_str_includes_origin_and_destination(self):
        origin = TravelHub(name="Port A")
        dest = TravelHub(name="Port B")
        route = TravelRoute(
            origin_hub=origin,
            destination_hub=dest,
            distance=100,
            travel_mode=TravelMode.SEA,
        )
        s = str(route)
        self.assertIn("Port A", s)
        self.assertIn("Port B", s)
        self.assertIn("Sea", s)


class TravelMethodModelTests(TestCase):
    def test_str(self):
        method = TravelMethod(
            name="Sailing Ship",
            travel_mode=TravelMode.SEA,
            base_speed=10.0,
        )
        self.assertEqual(str(method), "Sailing Ship")


class VoyageModelTests(TestCase):
    def test_default_status_is_draft(self):
        voyage = Voyage(route_hubs=[])
        self.assertEqual(voyage.status, VoyageStatus.DRAFT)

    def test_default_current_leg_index(self):
        voyage = Voyage(route_hubs=[])
        self.assertEqual(voyage.current_leg_index, 0)


class VoyageInviteModelTests(TestCase):
    def test_default_response_is_pending(self):
        from world.travel.models import VoyageInvite

        invite = VoyageInvite()
        self.assertEqual(invite.response, VoyageInvite.Response.PENDING)
