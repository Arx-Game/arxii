"""API tests for MissionGiverTargetSearchAPIView (#882 — typeclass-constrained
target picker for MissionGiver.target)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from evennia_extensions.models import RoomProfile
from world.areas.factories import AreaFactory


class MissionGiverTargetSearchAPIViewTests(TestCase):
    URL = "/api/mission-giver-targets/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-target-search", is_staff=True)
        cls.non_staff = AccountFactory(username="non-staff-target-search")

        cls.area = AreaFactory(name="Test District")

    def setUp(self) -> None:
        # Evennia ObjectDB instances (SharedMemoryModel) carry DbHolder
        # attributes that are un-deepcopyable. setUpTestData class attrs get
        # deep-copied per test method by Django's TestCase descriptor, so
        # ObjectDB objects must be created in setUp instead.
        super().setUp()
        self.room = ObjectDBFactory(
            db_key="Notice Board Plaza", db_typeclass_path="typeclasses.rooms.Room"
        )
        RoomProfile.objects.update_or_create(objectdb=self.room, defaults={"area": self.area})

        self.other_room = ObjectDBFactory(
            db_key="Other Room", db_typeclass_path="typeclasses.rooms.Room"
        )

        self.prop = ObjectDBFactory(
            db_key="Dusty Ledger", db_typeclass_path="typeclasses.objects.Object"
        )
        self.prop.db_location = self.room
        self.prop.save(update_fields=["db_location"])

        self.character = ObjectDBFactory(
            db_key="Some Character", db_typeclass_path="typeclasses.characters.Character"
        )

        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_non_staff_denied(self) -> None:
        self.client.force_authenticate(self.non_staff)
        resp = self.client.get(self.URL, {"kind": "room_trigger", "search": "Notice"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_kind_400(self) -> None:
        resp = self.client.get(self.URL, {"kind": "npc", "search": "x"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_room_search_returns_matching_room_with_area_hint(self) -> None:
        resp = self.client.get(self.URL, {"kind": "room_trigger", "search": "Notice"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            resp.json(),
            [{"id": self.room.pk, "name": "Notice Board Plaza", "hint": "Test District"}],
        )

    def test_environmental_detail_search_excludes_character(self) -> None:
        resp = self.client.get(
            self.URL, {"kind": "environmental_detail", "search": "Some Character"}
        )
        self.assertEqual(resp.json(), [])

    def test_environmental_detail_search_returns_prop_with_location_hint(self) -> None:
        resp = self.client.get(self.URL, {"kind": "environmental_detail", "search": "Dusty"})
        self.assertEqual(
            resp.json(),
            [{"id": self.prop.pk, "name": "Dusty Ledger", "hint": "Notice Board Plaza"}],
        )

    def test_id_lookup_returns_single_match(self) -> None:
        resp = self.client.get(self.URL, {"kind": "room_trigger", "id": self.room.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            resp.json(),
            {"id": self.room.pk, "name": "Notice Board Plaza", "hint": "Test District"},
        )

    def test_id_lookup_unknown_id_404(self) -> None:
        resp = self.client.get(self.URL, {"kind": "room_trigger", "id": 999999})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_id_lookup_wrong_kind_404(self) -> None:
        # self.prop is not a Room, so it 404s under kind=room_trigger.
        resp = self.client.get(self.URL, {"kind": "room_trigger", "id": self.prop.pk})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_id_lookup_non_numeric_id_400(self) -> None:
        resp = self.client.get(self.URL, {"kind": "room_trigger", "id": "abc"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
