from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
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
        response = self.client.get(f"/api/events/{event.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], event.name)

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
