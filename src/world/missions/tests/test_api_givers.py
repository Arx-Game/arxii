"""API tests for MissionGiverViewSet (#729 — trigger-based giver editor).

Covers the staff CRUD surface for the two surviving GiverKind variants
(ROOM_TRIGGER / ENVIRONMENTAL_DETAIL), the flat ``templates`` M2M draw
pool (Option A), the ?giver_kind filter, and that a (kind, target)
typeclass mismatch surfaces as a 400 (serializer-run model clean), not a
500 from save().
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.missions.constants import GiverKind
from world.missions.factories import MissionGiverFactory, MissionTemplateFactory


def _make_room():
    return ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")


class MissionGiverViewSetTests(TestCase):
    URL = "/api/missions/givers/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-giver-api", is_staff=True)
        cls.room = _make_room()
        cls.template = MissionTemplateFactory(name="giver-tmpl")

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_non_staff_denied(self) -> None:
        self.client.force_authenticate(AccountFactory(username="non-staff-giver"))
        self.assertEqual(self.client.get(self.URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_create_room_trigger_with_templates(self) -> None:
        resp = self.client.post(
            self.URL,
            {
                "name": "Notice Board",
                "giver_kind": GiverKind.ROOM_TRIGGER,
                "target": self.room.pk,
                "templates": [self.template.pk],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["templates"], [self.template.pk])
        self.assertTrue(resp.data["is_publishable"])

    def test_create_rejects_kind_target_typeclass_mismatch(self) -> None:
        """ROOM_TRIGGER pointed at a non-Room Object → 400 (model clean), not 500."""
        detail = ObjectDBFactory()  # plain Object typeclass, not a Room
        resp = self.client.post(
            self.URL,
            {
                "name": "Bad Giver",
                "giver_kind": GiverKind.ROOM_TRIGGER,
                "target": detail.pk,
                "templates": [],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_giver_kind(self) -> None:
        MissionGiverFactory(name="rt-giver", giver_kind=GiverKind.ROOM_TRIGGER, target=self.room)
        MissionGiverFactory(
            name="ed-giver",
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
            target=ObjectDBFactory(),
        )
        resp = self.client.get(self.URL, {"giver_kind": GiverKind.ENVIRONMENTAL_DETAIL})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [g["name"] for g in resp.data["results"]]
        self.assertIn("ed-giver", names)
        self.assertNotIn("rt-giver", names)

    def test_patch_templates(self) -> None:
        giver = MissionGiverFactory(
            name="patch-giver", giver_kind=GiverKind.ROOM_TRIGGER, target=self.room
        )
        resp = self.client.patch(
            f"{self.URL}{giver.pk}/",
            {"templates": [self.template.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        giver.refresh_from_db()
        self.assertEqual(list(giver.templates.values_list("pk", flat=True)), [self.template.pk])
