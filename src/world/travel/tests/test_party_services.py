"""Tests for voyage party formation services (#2352)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.travel.constants import TravelMode, VoyageStatus
from world.travel.factories import TravelHubFactory, TravelMethodFactory, TravelRouteFactory
from world.travel.models import Voyage, VoyageInvite, VoyageParticipant
from world.travel.services import (
    NotVoyageLeaderError,
    VoyageError,
    depart_voyage,
    invite_to_voyage,
    respond_to_voyage_invite,
)


def _make_persona():
    """Create a real Persona for FK assignment."""
    return PersonaFactory()


class InviteToVoyageTests(TestCase):
    """Unit tests for ``invite_to_voyage``."""

    def setUp(self):
        self.hub_a = TravelHubFactory(name="Hub A")
        self.hub_b = TravelHubFactory(name="Hub B", travel_modes=["LAND"])
        self.method = TravelMethodFactory(name="Walking", travel_mode=TravelMode.LAND)
        self.leader = _make_persona()
        self.invitee = _make_persona()
        self.voyage = Voyage.objects.create(
            leader=self.leader,
            travel_method=self.method,
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            route_hubs=[],
            status=VoyageStatus.DRAFT,
        )

    @patch("world.travel.services._check_colocated", return_value=True)
    def test_invites_colocated_character(self):
        """Leader can invite a co-located character to a DRAFT voyage."""
        invite = invite_to_voyage(self.voyage, self.leader, self.invitee)
        self.assertEqual(invite.response, VoyageInvite.Response.PENDING)
        self.assertEqual(invite.target_persona_id, self.invitee.pk)
        self.assertEqual(invite.invited_by_id, self.leader.pk)

    @patch("world.travel.services._check_colocated", return_value=True)
    def test_rejects_non_leader(self):
        """Non-leader cannot invite."""
        non_leader = _make_persona()
        with self.assertRaises(NotVoyageLeaderError):
            invite_to_voyage(self.voyage, non_leader, self.invitee)

    def test_rejects_when_not_draft(self):
        """Cannot invite to a non-DRAFT voyage."""
        self.voyage.status = VoyageStatus.IN_TRANSIT
        self.voyage.save()
        with self.assertRaises(VoyageError):
            invite_to_voyage(self.voyage, self.leader, self.invitee)

    @patch("world.travel.services._check_colocated", return_value=False)
    def test_rejects_not_colocated(self):
        """Cannot invite someone who isn't in the same room."""
        with self.assertRaises(VoyageError):
            invite_to_voyage(self.voyage, self.leader, self.invitee)

    @patch("world.travel.services._check_colocated", return_value=True)
    def test_rejects_duplicate_invite(self):
        """Cannot invite someone who's already invited."""
        VoyageInvite.objects.create(
            voyage=self.voyage, target_persona=self.invitee, invited_by=self.leader
        )
        with self.assertRaises(VoyageError):
            invite_to_voyage(self.voyage, self.leader, self.invitee)

    @patch("world.travel.services._check_colocated", return_value=True)
    def test_rejects_existing_participant(self):
        """Cannot invite someone who's already a participant."""
        VoyageParticipant.objects.create(voyage=self.voyage, persona=self.invitee)
        with self.assertRaises(VoyageError):
            invite_to_voyage(self.voyage, self.leader, self.invitee)


class RespondToVoyageInviteTests(TestCase):
    """Unit tests for ``respond_to_voyage_invite``."""

    def setUp(self):
        self.hub_a = TravelHubFactory(name="Hub A")
        self.hub_b = TravelHubFactory(name="Hub B", travel_modes=["LAND"])
        self.method = TravelMethodFactory(name="Walking", travel_mode=TravelMode.LAND)
        self.leader = _make_persona()
        self.invitee = _make_persona()
        self.voyage = Voyage.objects.create(
            leader=self.leader,
            travel_method=self.method,
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            route_hubs=[],
            status=VoyageStatus.DRAFT,
        )
        self.invite = VoyageInvite.objects.create(
            voyage=self.voyage, target_persona=self.invitee, invited_by=self.leader
        )

    def test_accept_sets_response(self):
        respond_to_voyage_invite(self.invite, VoyageInvite.Response.ACCEPTED)
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.response, VoyageInvite.Response.ACCEPTED)
        self.assertIsNotNone(self.invite.responded_at)

    def test_decline_sets_response(self):
        respond_to_voyage_invite(self.invite, VoyageInvite.Response.DECLINED)
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.response, VoyageInvite.Response.DECLINED)

    def test_rejects_double_response(self):
        self.invite.response = VoyageInvite.Response.ACCEPTED
        self.invite.save()
        with self.assertRaises(VoyageError):
            respond_to_voyage_invite(self.invite, VoyageInvite.Response.DECLINED)

    def test_rejects_when_voyage_not_draft(self):
        self.voyage.status = VoyageStatus.IN_TRANSIT
        self.voyage.save()
        with self.assertRaises(VoyageError):
            respond_to_voyage_invite(self.invite, VoyageInvite.Response.ACCEPTED)


class DepartVoyageTests(TestCase):
    """Unit tests for ``depart_voyage``."""

    def setUp(self):
        self.hub_a = TravelHubFactory(name="Hub A")
        self.hub_b = TravelHubFactory(name="Hub B", travel_modes=["LAND"])
        self.method = TravelMethodFactory(name="Walking", travel_mode=TravelMode.LAND)
        self.leader = _make_persona()
        self.voyage = Voyage.objects.create(
            leader=self.leader,
            travel_method=self.method,
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            route_hubs=[],
            status=VoyageStatus.DRAFT,
        )
        # Auto-enroll leader as participant (like start_voyage does)
        VoyageParticipant.objects.create(voyage=self.voyage, persona=self.leader)
        self.origin_room = self.hub_a.room_profile.objectdb

    @patch("world.travel.services._resolve_character_object")
    def test_depart_solo_computes_route(self, mock_resolve):
        """Solo depart with no invites computes route and transitions to IN_TRANSIT."""
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            distance=100,
            travel_mode=TravelMode.LAND,
        )
        mock_leader_obj = MagicMock()
        mock_leader_obj.location = self.origin_room
        mock_resolve.return_value = mock_leader_obj

        result = depart_voyage(self.voyage, self.leader)
        self.assertEqual(result.status, VoyageStatus.IN_TRANSIT)
        self.assertEqual(len(result.route_hubs), 2)
        self.assertEqual(result.route_hubs[0], self.hub_a.pk)
        self.assertEqual(result.route_hubs[1], self.hub_b.pk)

    @patch("world.travel.services._resolve_character_object")
    def test_depart_rejects_non_leader(self, mock_resolve):
        """Non-leader cannot depart."""
        mock_resolve.return_value = MagicMock(location=self.origin_room)
        non_leader = _make_persona()
        with self.assertRaises(NotVoyageLeaderError):
            depart_voyage(self.voyage, non_leader)

    @patch("world.travel.services._resolve_character_object")
    def test_depart_rejects_when_not_draft(self, mock_resolve):
        """Cannot depart a non-DRAFT voyage."""
        self.voyage.status = VoyageStatus.IN_TRANSIT
        self.voyage.route_hubs = [self.hub_a.pk, self.hub_b.pk]
        self.voyage.save()
        mock_resolve.return_value = MagicMock(location=self.origin_room)
        with self.assertRaises(VoyageError):
            depart_voyage(self.voyage, self.leader)

    @patch("world.travel.services._resolve_character_object")
    def test_depart_rejects_no_route(self, mock_resolve):
        """Depart raises if no route exists."""
        mock_resolve.return_value = MagicMock(location=self.origin_room)
        with self.assertRaises(VoyageError):
            depart_voyage(self.voyage, self.leader)

    @patch("world.travel.services._resolve_character_object")
    def test_depart_rejects_leader_moved(self, mock_resolve):
        """Depart raises if leader moved away from origin hub."""
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            distance=100,
            travel_mode=TravelMode.LAND,
        )
        # Leader is now at a different room
        mock_leader_obj = MagicMock()
        mock_leader_obj.location = MagicMock()  # different room
        mock_resolve.return_value = mock_leader_obj
        with self.assertRaises(VoyageError) as ctx:
            depart_voyage(self.voyage, self.leader)
        self.assertIn("Hub A", ctx.exception.user_message)

    @patch("world.travel.services._check_colocated", return_value=True)
    @patch("world.travel.services._resolve_character_object")
    def test_depart_enrolls_accepted_invitee(self, mock_resolve):
        """Depart enrolls accepted invitees who are co-located."""
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            distance=100,
            travel_mode=TravelMode.LAND,
        )
        mock_leader_obj = MagicMock()
        mock_leader_obj.location = self.origin_room
        mock_resolve.return_value = mock_leader_obj

        invitee = _make_persona()
        VoyageInvite.objects.create(
            voyage=self.voyage,
            target_persona=invitee,
            invited_by=self.leader,
            response=VoyageInvite.Response.ACCEPTED,
        )

        result = depart_voyage(self.voyage, self.leader)
        self.assertEqual(result.status, VoyageStatus.IN_TRANSIT)
        # Leader + accepted invitee = 2 participants
        self.assertEqual(result.participants.count(), 2)

    @patch("world.travel.services._check_colocated", return_value=False)
    @patch("world.travel.services._resolve_character_object")
    def test_depart_skips_moved_invitee(self, mock_resolve):
        """Depart silently skips accepted invitees who moved away."""
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            distance=100,
            travel_mode=TravelMode.LAND,
        )
        mock_leader_obj = MagicMock()
        mock_leader_obj.location = self.origin_room
        mock_resolve.return_value = mock_leader_obj

        invitee = _make_persona()
        VoyageInvite.objects.create(
            voyage=self.voyage,
            target_persona=invitee,
            invited_by=self.leader,
            response=VoyageInvite.Response.ACCEPTED,
        )

        result = depart_voyage(self.voyage, self.leader)
        # Only the leader (auto-enrolled) is a participant
        self.assertEqual(result.participants.count(), 1)

    @patch("world.travel.services._check_colocated", return_value=True)
    @patch("world.travel.services._resolve_character_object")
    def test_depart_leaves_pending_invitee(self, mock_resolve):
        """Depart does not enroll pending (unresolved) invitees."""
        TravelRouteFactory(
            origin_hub=self.hub_a,
            destination_hub=self.hub_b,
            distance=100,
            travel_mode=TravelMode.LAND,
        )
        mock_leader_obj = MagicMock()
        mock_leader_obj.location = self.origin_room
        mock_resolve.return_value = mock_leader_obj

        invitee = _make_persona()
        VoyageInvite.objects.create(
            voyage=self.voyage,
            target_persona=invitee,
            invited_by=self.leader,
            response=VoyageInvite.Response.PENDING,
        )

        result = depart_voyage(self.voyage, self.leader)
        # Only the leader — pending invitee not enrolled
        self.assertEqual(result.participants.count(), 1)
