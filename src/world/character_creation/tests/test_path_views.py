"""Tests for path-related views."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.classes.factories import PathFactory
from world.classes.models import PathStage


class PathViewSetTest(TestCase):
    """Tests for PathViewSet."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.steel = PathFactory(
            name="Path of Steel",
            stage=PathStage.PROSPECT,
            minimum_level=1,
            is_active=True,
        )
        cls.vanguard = PathFactory(
            name="Vanguard",
            stage=PathStage.POTENTIAL,
            minimum_level=3,
            is_active=True,
        )
        cls.inactive = PathFactory(
            name="Inactive Path",
            stage=PathStage.PROSPECT,
            minimum_level=1,
            is_active=False,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_list_returns_only_prospect_active_paths(self):
        """List endpoint returns only active Prospect paths."""
        response = self.client.get("/api/character-creation/paths/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [p["name"] for p in response.data]
        self.assertIn("Path of Steel", names)
        self.assertNotIn("Vanguard", names)  # Not Prospect
        self.assertNotIn("Inactive Path", names)  # Not active

    def test_retrieve_path(self):
        """Can retrieve a single path."""
        response = self.client.get(f"/api/character-creation/paths/{self.steel.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Path of Steel")

    def test_unauthenticated_access_denied(self):
        """Unauthenticated users cannot access paths."""
        self.client.logout()
        response = self.client.get("/api/character-creation/paths/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
