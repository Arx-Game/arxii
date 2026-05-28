"""Tests for MissionCategoryViewSet (GET /api/missions/categories/).

Read-only endpoint; staff-only. POST/PATCH/DELETE all return 405.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.missions.factories import MissionCategoryFactory

URL = "/api/missions/categories/"


class MissionCategoryEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-cat-ep-tc", is_staff=True)
        cls.cat_a = MissionCategoryFactory(name="courtly-cats", display_order=1)
        cls.cat_b = MissionCategoryFactory(name="heist-cats", display_order=2)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def test_list_returns_paginated_categories(self) -> None:
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("results", body)
        names = [c["name"] for c in body["results"]]
        self.assertIn("courtly-cats", names)
        self.assertIn("heist-cats", names)

    def test_list_shape_includes_id_name_description_order(self) -> None:
        res = self.client.get(URL)
        first = res.json()["results"][0]
        self.assertEqual(set(first.keys()), {"id", "name", "description", "display_order"})

    def test_detail_by_pk(self) -> None:
        res = self.client.get(f"{URL}{self.cat_a.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["name"], "courtly-cats")

    def test_post_returns_405(self) -> None:
        res = self.client.post(URL, {"name": "new-cat"}, format="json")
        self.assertEqual(res.status_code, 405)

    def test_patch_returns_405(self) -> None:
        res = self.client.patch(f"{URL}{self.cat_a.pk}/", {"name": "x"}, format="json")
        self.assertEqual(res.status_code, 405)

    def test_delete_returns_405(self) -> None:
        res = self.client.delete(f"{URL}{self.cat_a.pk}/")
        self.assertEqual(res.status_code, 405)

    def test_non_staff_forbidden(self) -> None:
        non_staff = AccountFactory(username="player-cat-ep-tc", is_staff=False)
        client = APIClient()
        client.force_authenticate(user=non_staff)
        res = client.get(URL)
        self.assertEqual(res.status_code, 403)
