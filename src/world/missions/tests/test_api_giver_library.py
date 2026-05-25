"""Phase D D3: giver library viewsets (MissionGiver + Offering + Standing).

Staff CRUD for the offer-side surface. Giver is slug-keyed; the
serializer mirrors the model's typeclass-validating clean() so invalid
target/kind combos return 400.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.missions.constants import GiverKind
from world.missions.factories import (
    MissionGiverFactory,
    MissionGiverOfferingFactory,
    MissionGiverStandingFactory,
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
            slug="lockbreaker",
            giver_kind=GiverKind.ROOM_TRIGGER,
            target=cls.room,
            org=cls.org,
        )
        MissionGiverFactory(name="Bare Drafty", slug="bare-drafty", giver_kind=GiverKind.NPC)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_org_name(self) -> None:
        response = self.client.get(self.URL, {"org_name": "Crime Guild"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in response.data["results"]}
        self.assertEqual(slugs, {"lockbreaker"})

    def test_detail_slug_lookup(self) -> None:
        response = self.client.get(f"{self.URL}lockbreaker/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "The Lockbreaker")
        self.assertTrue(response.data["is_publishable"])

    def test_detail_drafty_giver_not_publishable(self) -> None:
        response = self.client.get(f"{self.URL}bare-drafty/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_publishable"])

    def test_create_room_trigger(self) -> None:
        room = _room()
        response = self.client.post(
            self.URL,
            {
                "name": "Brand New",
                "slug": "brand-new",
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
                "slug": "bad-combo",
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
        cls.giver = MissionGiverFactory(slug="off-giver")
        cls.template = MissionTemplateFactory(slug="off-tmpl")
        MissionGiverOfferingFactory(giver=cls.giver, template=cls.template)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_giver(self) -> None:
        response = self.client.get(self.URL, {"giver": self.giver.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_create_with_weight_override(self) -> None:
        other = MissionTemplateFactory(slug="off-tmpl-2")
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
        other = MissionTemplateFactory(slug="off-tmpl-3")
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


class StandingViewSetTests(TestCase):
    URL = "/api/missions/giver-standings/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = _staff_account("staff-std-vs")
        cls.giver = MissionGiverFactory(slug="std-giver")
        cls.character = CharacterFactory()
        cls.standing = MissionGiverStandingFactory(
            giver=cls.giver, character=cls.character, affection=42
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_giver(self) -> None:
        response = self.client.get(self.URL, {"giver": self.giver.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_patch_clears_cooldown(self) -> None:
        # Staff override: set available_at to now to clear the cooldown.
        response = self.client.patch(
            f"{self.URL}{self.standing.pk}/",
            {"available_at": timezone.now().isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_patch_adjusts_affection(self) -> None:
        response = self.client.patch(
            f"{self.URL}{self.standing.pk}/",
            {"affection": -10},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["affection"], -10)

    def test_create_new_standing(self) -> None:
        other_giver = MissionGiverFactory(slug="std-other")
        response = self.client.post(
            self.URL,
            {
                "giver": other_giver.pk,
                "character": self.character.pk,
                "available_at": (timezone.now() + timedelta(days=1)).isoformat(),
                "affection": 0,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
