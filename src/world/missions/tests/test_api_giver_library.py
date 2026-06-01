"""Phase D D3: giver library viewsets (MissionGiver + Offering + Standing).

Staff CRUD for the offer-side surface. Giver is slug-keyed; the
serializer mirrors the model's typeclass-validating clean() so invalid
target/kind combos return 400.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    ObjectDBFactory,
)
from world.missions.constants import GiverKind
from world.missions.factories import (
    MissionGiverFactory,
    MissionGiverOfferingFactory,
    MissionTemplateFactory,
)
from world.societies.factories import OrganizationFactory


def _staff_account(username: str) -> object:
    return AccountFactory(username=username, is_staff=True)


def _room() -> object:
    return ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")


class GiverViewSetTests(TestCase):
    URL = "/api/missions/givers/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = _staff_account("staff-giver-vs")
        cls.org = OrganizationFactory(name="Crime Guild")
        cls.room = _room()
        cls.giver = MissionGiverFactory(
            name="The Lockbreaker",
            giver_kind=GiverKind.ROOM_TRIGGER,
            target=cls.room,
            org=cls.org,
        )
        cls.drafty = MissionGiverFactory(name="Bare Drafty", giver_kind=GiverKind.NPC)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_org_name(self) -> None:
        response = self.client.get(self.URL, {"org_name": "Crime Guild"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {row["name"] for row in response.data["results"]}
        self.assertEqual(names, {"The Lockbreaker"})

    def test_detail_pk_lookup(self) -> None:
        response = self.client.get(f"{self.URL}{self.giver.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "The Lockbreaker")
        self.assertTrue(response.data["is_publishable"])

    def test_detail_drafty_giver_not_publishable(self) -> None:
        response = self.client.get(f"{self.URL}{self.drafty.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_publishable"])

    def test_create_room_trigger(self) -> None:
        room = _room()
        response = self.client.post(
            self.URL,
            {
                "name": "Brand New",
                "giver_kind": GiverKind.ROOM_TRIGGER,
                "target": room.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_create_rejects_npc_with_room_target(self) -> None:
        # Wrong typeclass for kind — model clean() rejects.
        room = _room()
        response = self.client.post(
            self.URL,
            {
                "name": "Bad Combo",
                "giver_kind": GiverKind.NPC,
                "target": room.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class OfferingViewSetTests(TestCase):
    URL = "/api/missions/giver-offerings/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = _staff_account("staff-off-vs")
        cls.giver = MissionGiverFactory(name="off-giver")
        cls.template = MissionTemplateFactory(name="off-tmpl")
        MissionGiverOfferingFactory(giver=cls.giver, template=cls.template)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_giver(self) -> None:
        response = self.client.get(self.URL, {"giver": self.giver.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_create_with_weight_override(self) -> None:
        other = MissionTemplateFactory(name="off-tmpl-2")
        response = self.client.post(
            self.URL,
            {
                "giver": self.giver.pk,
                "template": other.pk,
                "weight_override": 7,
                "requirements_override": {},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["weight_override"], 7)

    def test_create_rejects_zero_weight_override(self) -> None:
        other = MissionTemplateFactory(name="off-tmpl-3")
        response = self.client.post(
            self.URL,
            {
                "giver": self.giver.pk,
                "template": other.pk,
                "weight_override": 0,
                "requirements_override": {},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# NPCStanding CRUD API tests moved to
# world.npc_services.tests.test_api_standings — the standing model
# relocated as part of the unified NPC service framework.
