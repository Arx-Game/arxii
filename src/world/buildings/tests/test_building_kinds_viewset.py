"""BuildingKind catalog read endpoint (#1882).

Public read — BuildingKind is an open admin-authored catalog. The endpoint
returns all rows with id, name, description, and the nine descriptive flags.
"""

from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.buildings.models import BuildingKind


@tag("sqlite_safe")
class BuildingKindViewSetTests(APITestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.house = BuildingKind.objects.create(
            name="House",
            description="A residential dwelling.",
            is_residential=True,
        )
        self.tavern = BuildingKind.objects.create(
            name="Tavern",
            description="A commercial gathering place.",
            is_commercial=True,
            is_maritime=True,
        )
        self.fortress = BuildingKind.objects.create(
            name="Fortress",
            description="A fortified hold.",
            is_fortified=True,
            is_subterranean=True,
        )

    def _get(self, url="/api/buildings/building-kinds/", **params):
        self.client.force_authenticate(user=self.account)
        return self.client.get(url, params)

    def test_requires_authentication(self) -> None:
        response = self.client.get("/api/buildings/building-kinds/")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_lists_all_kinds_with_flags(self) -> None:
        response = self._get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        names = {row["name"] for row in results}
        self.assertEqual(names, {"House", "Tavern", "Fortress"})

        house = next(row for row in results if row["name"] == "House")
        self.assertEqual(house["description"], "A residential dwelling.")
        self.assertTrue(house["is_residential"])
        self.assertFalse(house["is_commercial"])
        self.assertFalse(house["is_fortified"])
        self.assertFalse(house["is_occult"])
        self.assertFalse(house["is_maritime"])
        self.assertFalse(house["is_agrarian"])
        self.assertFalse(house["is_aerial"])
        self.assertFalse(house["is_subterranean"])
        self.assertFalse(house["is_secret"])

        tavern = next(row for row in results if row["name"] == "Tavern")
        self.assertTrue(tavern["is_commercial"])
        self.assertTrue(tavern["is_maritime"])

        fortress = next(row for row in results if row["name"] == "Fortress")
        self.assertTrue(fortress["is_fortified"])
        self.assertTrue(fortress["is_subterranean"])

    def test_results_are_paginated(self) -> None:
        response = self._get()
        data = response.json()
        self.assertIn("results", data)
        self.assertIn("count", data)
        self.assertEqual(data["count"], 3)

    def test_search_filters_by_name(self) -> None:
        response = self._get(search="Tavern")
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Tavern")

    def test_urban_seed_kinds_appear_in_catalog(self) -> None:
        """Seed-authored urban kinds appear in the catalog endpoint."""
        from world.buildings.seeds import ensure_urban_building_kinds

        ensure_urban_building_kinds()
        response = self._get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {row["name"] for row in response.json()["results"]}
        # The 3 manually-created kinds + 6 seeded urban kinds
        for expected in ("Cottage", "Tavern", "Shop", "Workshop", "Guild Hall", "Warehouse"):
            self.assertIn(expected, names)

        cottage = next(row for row in response.json()["results"] if row["name"] == "Cottage")
        self.assertTrue(cottage["is_residential"])
        self.assertFalse(cottage["is_commercial"])
