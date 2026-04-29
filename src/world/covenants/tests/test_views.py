"""Tests for covenants API views."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.covenants.factories import CovenantRoleFactory, GearArchetypeCompatibilityFactory
from world.items.constants import GearArchetype


class CovenantsViewTestCase(TestCase):
    """Base test case with authenticated API client."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        cls.user = AccountDB.objects.create_user(
            username="covtestuser",
            email="cov@test.com",
            password="testpass123",
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class GearArchetypeCompatibilityViewTests(CovenantsViewTestCase):
    """Tests for GET /api/covenants/gear-compatibilities/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.role = CovenantRoleFactory(name="Sword")
        cls.compat = GearArchetypeCompatibilityFactory(
            covenant_role=cls.role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )

    def test_list_returns_compatibilities(self) -> None:
        """GET list returns seeded compatibility row."""
        response = self.client.get("/api/covenants/gear-compatibilities/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data]
        self.assertIn(self.compat.pk, ids)

    def test_filter_by_covenant_role(self) -> None:
        """Filter by ?covenant_role= narrows to rows for that role only."""
        other_role = CovenantRoleFactory(name="Shield")
        GearArchetypeCompatibilityFactory(
            covenant_role=other_role,
            gear_archetype=GearArchetype.LIGHT_ARMOR,
        )
        response = self.client.get(
            "/api/covenants/gear-compatibilities/", {"covenant_role": self.role.pk}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) >= 1)
        for row in response.data:
            self.assertEqual(row["covenant_role"], self.role.pk)

    def test_filter_by_gear_archetype(self) -> None:
        """Filter by ?gear_archetype= narrows to rows with that archetype."""
        response = self.client.get(
            "/api/covenants/gear-compatibilities/",
            {"gear_archetype": GearArchetype.HEAVY_ARMOR},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) >= 1)
        for row in response.data:
            self.assertEqual(row["gear_archetype"], GearArchetype.HEAVY_ARMOR)

    def test_detail_endpoint(self) -> None:
        """GET single row by pk returns the correct record."""
        response = self.client.get(f"/api/covenants/gear-compatibilities/{self.compat.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.compat.pk)
        self.assertEqual(response.data["covenant_role"], self.role.pk)
        self.assertEqual(response.data["gear_archetype"], GearArchetype.HEAVY_ARMOR)
        self.assertIn("gear_archetype_display", response.data)

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests receive 403."""
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get("/api/covenants/gear-compatibilities/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_method_not_allowed(self) -> None:
        """Read-only ViewSet: POST returns 405 Method Not Allowed."""
        response = self.client.post(
            "/api/covenants/gear-compatibilities/",
            {"covenant_role": self.role.pk, "gear_archetype": GearArchetype.HEAVY_ARMOR},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
