"""Tests for the character-creation families endpoint's area_id filter (#3003).

``getFamilies(areaId)`` (frontend/src/character-creation/api.ts) sends
``area_id`` to ``GET /api/character-creation/families/``, which is served by
the live ``world.roster.views.FamilyViewSet`` / ``FamilyFilterSet``. Before
this fix, that filterset declared only ``has_open_positions`` — django-filter
silently drops unknown query params, so the CG Lineage stage's family list was
not filtered by starting area at all.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import RealmFactory, StartingAreaFactory
from world.roster.factories import FamilyFactory


class FamilyAreaFilterTest(TestCase):
    """``area_id`` on the character-creation families endpoint filters by realm."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.realm_a = RealmFactory(name="Realm A")
        cls.realm_b = RealmFactory(name="Realm B")
        cls.area_a = StartingAreaFactory(name="Area A", realm=cls.realm_a)
        cls.area_b = StartingAreaFactory(name="Area B", realm=cls.realm_b)

        cls.family_a = FamilyFactory(name="House A", origin_realm=cls.realm_a)
        cls.family_b = FamilyFactory(name="House B", origin_realm=cls.realm_b)
        cls.family_unaffiliated = FamilyFactory(name="House Unaffiliated", origin_realm=None)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_area_id_filters_families_by_realm(self):
        """Only families matching the area's realm (or unaffiliated) come back."""
        response = self.client.get(f"/api/character-creation/families/?area_id={self.area_a.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {f["name"] for f in response.data}
        self.assertIn("House A", names)
        self.assertIn("House Unaffiliated", names)
        self.assertNotIn("House B", names)

    def test_no_area_id_returns_all_playable_families(self):
        """Without area_id, no realm filtering happens."""
        response = self.client.get("/api/character-creation/families/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {f["name"] for f in response.data}
        self.assertIn("House A", names)
        self.assertIn("House B", names)
        self.assertIn("House Unaffiliated", names)
