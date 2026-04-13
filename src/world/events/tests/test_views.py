from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.events.constants import EventStatus, InvitationTargetType
from world.events.factories import EventFactory, EventHostFactory, EventInvitationFactory
from world.events.models import EventInvitation
from world.events.services import start_event
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import PersonaFactory, SceneParticipationFactory
from world.scenes.models import Scene


class EventViewSetTestCase(APITestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def test_list_returns_events(self) -> None:
        EventFactory(is_public=True)
        response = self.client.get("/api/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_event_detail(self) -> None:
        event = EventFactory()
        EventHostFactory(event=event)
        # Public event — visible to any authenticated user
        response = self.client.get(f"/api/events/{event.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], event.name)

    def test_retrieve_private_event_returns_404_for_non_invitee(self) -> None:
        """Non-host, non-invitee cannot retrieve a private event by ID."""
        # Give the requesting user a persona
        identity = CharacterSheetFactory()
        RosterTenureFactory(
            roster_entry__character_sheet__character=identity.character,
            player_data__account=self.account,
        )
        # Create a private event hosted by someone else
        private_event = EventFactory(is_public=False)
        EventHostFactory(event=private_event)
        response = self.client.get(f"/api/events/{private_event.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_schedule_action(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        host = EventHostFactory(event=event)
        RosterTenureFactory(
            roster_entry__character_sheet__character=host.persona.character_sheet.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.SCHEDULED)

    def test_schedule_wrong_status_returns_400(self) -> None:
        event = EventFactory(status=EventStatus.ACTIVE)
        host = EventHostFactory(event=event)
        RosterTenureFactory(
            roster_entry__character_sheet__character=host.persona.character_sheet.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_start_action(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        host = EventHostFactory(event=event)
        RosterTenureFactory(
            roster_entry__character_sheet__character=host.persona.character_sheet.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/start/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.ACTIVE)

    def test_complete_action(self) -> None:
        event = EventFactory(status=EventStatus.ACTIVE)
        host = EventHostFactory(event=event)
        RosterTenureFactory(
            roster_entry__character_sheet__character=host.persona.character_sheet.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/complete/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.COMPLETED)

    def test_cancel_action(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        host = EventHostFactory(event=event)
        RosterTenureFactory(
            roster_entry__character_sheet__character=host.persona.character_sheet.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/cancel/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.CANCELLED)

    @suppress_permission_errors
    def test_non_host_cannot_schedule(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        EventHostFactory(event=event)  # host is someone else
        response = self.client.post(f"/api/events/{event.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_schedule_any_event(self) -> None:
        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        event = EventFactory(status=EventStatus.DRAFT)
        EventHostFactory(event=event)
        response = self.client.post(f"/api/events/{event.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_status(self) -> None:
        EventFactory(status=EventStatus.SCHEDULED)
        EventFactory(status=EventStatus.COMPLETED)
        response = self.client.get("/api/events/", {"status": "scheduled"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for event_data in response.data["results"]:
            self.assertEqual(event_data["status"], "scheduled")

    def test_search_by_name(self) -> None:
        EventFactory(name="Grand Ball")
        EventFactory(name="Secret Meeting")
        response = self.client.get("/api/events/", {"search": "Ball"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], "Grand Ball")

    def test_unauthenticated_cannot_create(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.post("/api/events/", {"name": "Test"})
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_unauthenticated_can_list_public(self) -> None:
        EventFactory(is_public=True)
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_hides_private_events_from_non_invitee(self) -> None:
        """User with a persona but not invited cannot see private events."""
        # Give the requesting user a persona via the standard identity chain
        identity = CharacterSheetFactory()
        RosterTenureFactory(
            roster_entry__character_sheet__character=identity.character,
            player_data__account=self.account,
        )
        # Create a private event hosted by someone else entirely
        private_event = EventFactory(is_public=False)
        EventHostFactory(event=private_event)
        response = self.client.get("/api/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should not see the private event
        for event_data in response.data["results"]:
            self.assertTrue(event_data["is_public"])

    def test_list_shows_private_events_to_host(self) -> None:
        private_event = EventFactory(is_public=False)
        identity = CharacterSheetFactory()
        primary_persona = identity.primary_persona
        host = EventHostFactory(event=private_event, persona=primary_persona)
        RosterTenureFactory(
            roster_entry__character_sheet__character=host.persona.character_sheet.character,
            player_data__account=self.account,
        )
        response = self.client.get("/api/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event_ids = [e["id"] for e in response.data["results"]]
        self.assertIn(private_event.id, event_ids)

    def test_list_excludes_cancelled_events(self) -> None:
        EventFactory(is_public=True, status=EventStatus.CANCELLED)
        response = self.client.get("/api/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for event_data in response.data["results"]:
            self.assertNotEqual(event_data["status"], "cancelled")

    def test_scene_gm_can_complete_event(self) -> None:
        """A scene GM (not a host) can complete an active event."""
        event = EventFactory(status=EventStatus.SCHEDULED)
        EventHostFactory(event=event)  # host is someone else
        start_event(event)
        scene = Scene.objects.get(event=event)
        SceneParticipationFactory(scene=scene, account=self.account, is_gm=True)
        response = self.client.post(f"/api/events/{event.id}/complete/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.COMPLETED)

    def test_detail_includes_is_gm_field(self) -> None:
        """Event detail response includes is_gm for scene GMs."""
        event = EventFactory(status=EventStatus.SCHEDULED)
        EventHostFactory(event=event)
        start_event(event)
        scene = Scene.objects.get(event=event)
        SceneParticipationFactory(scene=scene, account=self.account, is_gm=True)
        response = self.client.get(f"/api/events/{event.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_gm"])

    def test_detail_is_gm_false_for_non_gm(self) -> None:
        """Event detail response has is_gm=False for non-GMs."""
        event = EventFactory(is_public=True)
        EventHostFactory(event=event)
        response = self.client.get(f"/api/events/{event.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_gm"])

    @suppress_permission_errors
    def test_scene_gm_cannot_cancel_event(self) -> None:
        """A scene GM cannot cancel an event — only hosts/staff."""
        event = EventFactory(status=EventStatus.SCHEDULED)
        EventHostFactory(event=event)  # host is someone else
        start_event(event)
        scene = Scene.objects.get(event=event)
        SceneParticipationFactory(scene=scene, account=self.account, is_gm=True)
        response = self.client.post(f"/api/events/{event.id}/cancel/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class EventInvitationViewSetTestCase(APITestCase):
    """Tests for the EventInvitationViewSet (create/destroy)."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)
        identity = CharacterSheetFactory()
        self.host_persona = identity.primary_persona
        self.event = EventFactory(status=EventStatus.DRAFT)
        EventHostFactory(event=self.event, persona=self.host_persona)
        RosterTenureFactory(
            roster_entry__character_sheet__character=identity.character,
            player_data__account=self.account,
        )

    def _invite_url(self) -> str:
        return "/api/events/invitations/"

    def _invite_data(self, target_id: int, target_type: str = "persona") -> dict:
        return {
            "event": self.event.id,
            "target_type": target_type,
            "target_id": target_id,
        }

    def test_create_invitation(self) -> None:
        target = PersonaFactory()
        response = self.client.post(self._invite_url(), self._invite_data(target.id), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            EventInvitation.objects.filter(
                event=self.event,
                target_type=InvitationTargetType.PERSONA,
                target_persona=target,
            ).exists()
        )

    def test_create_returns_invitation_data(self) -> None:
        target = PersonaFactory()
        response = self.client.post(self._invite_url(), self._invite_data(target.id), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["target_name"], target.name)

    def test_duplicate_invite_returns_409(self) -> None:
        target = PersonaFactory()
        EventInvitationFactory(
            event=self.event,
            target_type=InvitationTargetType.PERSONA,
            target_persona=target,
        )
        response = self.client.post(self._invite_url(), self._invite_data(target.id), format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_invite_nonexistent_target_returns_404(self) -> None:
        response = self.client.post(self._invite_url(), self._invite_data(999999), format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invite_to_active_event_returns_400(self) -> None:
        self.event.status = EventStatus.ACTIVE
        self.event.save(update_fields=["status"])
        target = PersonaFactory()
        response = self.client.post(self._invite_url(), self._invite_data(target.id), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @suppress_permission_errors
    def test_non_host_cannot_invite(self) -> None:
        other_account = AccountFactory()
        self.client.force_authenticate(user=other_account)
        target = PersonaFactory()
        response = self.client.post(self._invite_url(), self._invite_data(target.id), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_destroy_invitation(self) -> None:
        invitation = EventInvitationFactory(event=self.event)
        response = self.client.delete(f"/api/events/invitations/{invitation.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(EventInvitation.objects.filter(id=invitation.id).exists())

    @suppress_permission_errors
    def test_non_host_cannot_destroy_invitation(self) -> None:
        other_account = AccountFactory()
        self.client.force_authenticate(user=other_account)
        invitation = EventInvitationFactory(event=self.event)
        response = self.client.delete(f"/api/events/invitations/{invitation.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(EventInvitation.objects.filter(id=invitation.id).exists())

    def test_destroy_on_active_event_returns_400(self) -> None:
        self.event.status = EventStatus.ACTIVE
        self.event.save(update_fields=["status"])
        invitation = EventInvitationFactory(event=self.event)
        response = self.client.delete(f"/api/events/invitations/{invitation.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invite_with_invited_by_persona(self) -> None:
        target = PersonaFactory()
        data = self._invite_data(target.id)
        data["invited_by_persona"] = self.host_persona.id
        response = self.client.post(self._invite_url(), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        inv = EventInvitation.objects.get(event=self.event, target_persona=target)
        self.assertEqual(inv.invited_by_id, self.host_persona.id)
