from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.events.constants import EventStatus
from world.events.factories import EventFactory, EventHostFactory
from world.roster.factories import RosterTenureFactory


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
        identity = CharacterIdentityFactory()
        RosterTenureFactory(
            roster_entry__character=identity.character,
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
            roster_entry__character=host.persona.character,
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
            roster_entry__character=host.persona.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_start_action(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        host = EventHostFactory(event=event)
        RosterTenureFactory(
            roster_entry__character=host.persona.character,
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
            roster_entry__character=host.persona.character,
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
            roster_entry__character=host.persona.character,
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
        identity = CharacterIdentityFactory()
        RosterTenureFactory(
            roster_entry__character=identity.character,
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
        identity = CharacterIdentityFactory()
        primary_persona = identity.active_persona
        host = EventHostFactory(event=private_event, persona=primary_persona)
        RosterTenureFactory(
            roster_entry__character=host.persona.character,
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
