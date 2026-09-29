"""Anonymous shop-window reads for CG content (#3305, ADR-0224 precedent)."""

from django.test import TestCase
from rest_framework.test import APIClient

from world.character_creation.factories import (
    BeginningsFactory,
    RealmFactory,
    StartingAreaFactory,
)


class PublicCGReadsTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = RealmFactory(name="Arx", theme="arx")
        cls.area = StartingAreaFactory(
            name="The City of Arx",
            description="PLACEHOLDER hook",
            realm=cls.realm,
            is_active=True,
        )
        cls.open_beginning = BeginningsFactory(
            name="The Caretaker",
            description="PLACEHOLDER hook",
            starting_area=cls.area,
        )
        cls.inactive_beginning = BeginningsFactory(
            name="The Hidden One",
            description="secret",
            starting_area=cls.area,
            is_active=False,
        )

    def setUp(self) -> None:
        self.client = APIClient()  # anonymous

    def test_anonymous_lists_starting_areas(self) -> None:
        resp = self.client.get("/api/character-creation/starting-areas/")
        self.assertEqual(resp.status_code, 200)
        names = [row["name"] for row in resp.json()]
        self.assertIn("The City of Arx", names)
        row = next(r for r in resp.json() if r["name"] == "The City of Arx")
        self.assertEqual(row["realm_theme"], "arx")

    def test_starting_area_carries_its_realms_formal_name(self) -> None:
        """The Origin stage's tag is the name staff wrote on the realm (#4078)."""
        realm = RealmFactory(
            name="Aythirmok", formal_name="The Kingdom of Aythirmok", theme="aythirmok"
        )
        StartingAreaFactory(name="The Bonespire", realm=realm, is_active=True)
        resp = self.client.get("/api/character-creation/starting-areas/")
        row = next(r for r in resp.json() if r["name"] == "The Bonespire")
        self.assertEqual(row["realm_formal_name"], "The Kingdom of Aythirmok")
        self.assertEqual(row["realm_name"], "Aythirmok")

    def test_starting_area_formal_name_is_blank_when_the_realm_has_none(self) -> None:
        row = next(
            r
            for r in self.client.get("/api/character-creation/starting-areas/").json()
            if r["name"] == "The City of Arx"
        )
        self.assertEqual(row["realm_formal_name"], "")
        self.assertEqual(row["realm_name"], "Arx")

    def test_starting_area_with_no_realm_carries_no_realm_names(self) -> None:
        StartingAreaFactory(name="Nowhere Yet", realm=None, is_active=True)
        row = next(
            r
            for r in self.client.get("/api/character-creation/starting-areas/").json()
            if r["name"] == "Nowhere Yet"
        )
        self.assertIsNone(row["realm_formal_name"])
        self.assertIsNone(row["realm_name"])

    def test_anonymous_lists_active_beginnings_only(self) -> None:
        resp = self.client.get(f"/api/character-creation/beginnings/?starting_area={self.area.pk}")
        self.assertEqual(resp.status_code, 200)
        names = [row["name"] for row in resp.json()]
        self.assertIn("The Caretaker", names)
        self.assertNotIn("The Hidden One", names)
