"""Tests for DRAFT status guards on voyage services (#2352)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.travel.constants import TravelMode, VoyageStatus
from world.travel.factories import TravelHubFactory, TravelMethodFactory
from world.travel.models import Voyage, VoyageParticipant
from world.travel.services import (
    VoyageError,
    abandon_voyage,
    advance_leg,
    complete_voyage,
)


class DraftGuardTests(TestCase):
    """Ensure advance_leg/complete_voyage reject DRAFT voyages and abandon_voyage allows DRAFT."""

    def setUp(self):
        self.hub_a = TravelHubFactory(name="Hub A")
        self.hub_b = TravelHubFactory(name="Hub B", travel_modes=["LAND"])
        self.method = TravelMethodFactory(name="Walking", travel_mode=TravelMode.LAND)
        self.leader = PersonaFactory()
        self.voyage = Voyage.objects.create(
            leader=self.leader,
            travel_method=self.method,
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            route_hubs=[],
            status=VoyageStatus.DRAFT,
        )
        VoyageParticipant.objects.create(voyage=self.voyage, persona=self.leader)

    def test_advance_leg_rejects_draft(self):
        """advance_leg on a DRAFT voyage raises 'You must depart first.'"""
        with self.assertRaises(VoyageError) as ctx:
            advance_leg(self.voyage, caller=self.leader)
        self.assertIn("depart", ctx.exception.user_message.lower())

    def test_complete_voyage_rejects_draft(self):
        """complete_voyage on a DRAFT voyage raises 'You must depart first.'"""
        with self.assertRaises(VoyageError) as ctx:
            complete_voyage(self.voyage, caller=self.leader)
        self.assertIn("depart", ctx.exception.user_message.lower())

    @patch("world.travel.services._resolve_character_object")
    def test_abandon_voyage_allows_draft(self, mock_resolve):
        """abandon_voyage on a DRAFT voyage succeeds (leader cancels draft)."""
        mock_resolve.return_value = MagicMock()
        abandon_voyage(self.voyage, caller=self.leader)
        self.voyage.refresh_from_db()
        self.assertEqual(self.voyage.status, VoyageStatus.ABANDONED)
