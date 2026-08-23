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
            trust_required=0,
        )
        cls.gated_beginning = BeginningsFactory(
            name="The Hidden One",
            description="secret",
            starting_area=cls.area,
            trust_required=50,
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

    def test_anonymous_lists_open_beginnings_only(self) -> None:
        resp = self.client.get(f"/api/character-creation/beginnings/?starting_area={self.area.pk}")
        self.assertEqual(resp.status_code, 200)
        names = [row["name"] for row in resp.json()]
        self.assertIn("The Caretaker", names)
        self.assertNotIn("The Hidden One", names)
