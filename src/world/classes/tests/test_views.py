"""
Tests for Classes API views.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.classes.factories import (
    AspectFactory,
    CharacterClassFactory,
    PathAspectFactory,
    PathFactory,
)
from world.classes.models import PathStage


class ClassesAPITestCase(TestCase):
    """Base test case with authenticated API client."""

    @classmethod
    def setUpTestData(cls):
        from evennia.accounts.models import AccountDB

        cls.user = AccountDB.objects.create_user(
            username="testuser",
            email="test@test.com",
            password="testpass123",
        )
        cls.staff_user = AccountDB.objects.create_user(
            username="staffuser",
            email="staff@test.com",
            password="testpass123",
        )
        cls.staff_user.is_staff = True
        cls.staff_user.save()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class PathViewSetTests(ClassesAPITestCase):
    """Tests for PathViewSet."""

    def test_list_paths(self):
        """List endpoint returns active paths."""
        path = PathFactory()
        response = self.client.get("/api/classes/paths/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], path.name)

    def test_list_only_active(self):
        """List endpoint only returns active paths by default."""
        PathFactory(is_active=True)
        PathFactory(is_active=False)
        response = self.client.get("/api/classes/paths/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_filter_by_is_active(self):
        """Can explicitly filter paths by is_active."""
        PathFactory(is_active=True)
        PathFactory(is_active=False)

        response = self.client.get("/api/classes/paths/?is_active=false")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_filter_by_stage(self):
        """Can filter paths by stage."""
        PathFactory(stage=PathStage.PROSPECT)
        PathFactory(stage=PathStage.PUISSANT, minimum_level=6)
        response = self.client.get(f"/api/classes/paths/?stage={PathStage.PROSPECT}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_excludes_aspects(self):
        """List serializer does not include aspects."""
        path = PathFactory()
        PathAspectFactory(character_path=path)
        response = self.client.get("/api/classes/paths/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("aspects", response.data[0])

    def test_list_includes_stage_display(self):
        """List serializer includes human-readable stage display."""
        PathFactory(stage=PathStage.PROSPECT)
        response = self.client.get("/api/classes/paths/")
        self.assertEqual(response.data[0]["stage_display"], "Prospect")

    def test_retrieve_with_aspects(self):
        """Retrieve endpoint returns path with aspects."""
        path = PathFactory()
        pa = PathAspectFactory(character_path=path)
        response = self.client.get(f"/api/classes/paths/{path.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], path.name)
        self.assertEqual(len(response.data["aspects"]), 1)
        self.assertEqual(response.data["aspects"][0]["aspect_name"], pa.aspect.name)
        # Weight should NOT be in the response
        self.assertNotIn("weight", response.data["aspects"][0])

    def test_retrieve_with_parent_paths(self):
        """Retrieve endpoint includes parent path ids."""
        parent = PathFactory(stage=PathStage.PROSPECT)
        child = PathFactory(stage=PathStage.POTENTIAL, minimum_level=3)
        child.parent_paths.add(parent)
        response = self.client.get(f"/api/classes/paths/{child.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["parent_path_ids"], [parent.id])

    def test_unauthenticated_denied(self):
        """Unauthenticated requests are denied."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/classes/paths/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CharacterClassViewSetTests(ClassesAPITestCase):
    """Tests for CharacterClassViewSet."""

    def test_list_classes(self):
        """List endpoint returns visible classes."""
        cc = CharacterClassFactory()
        response = self.client.get("/api/classes/classes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], cc.name)

    def test_hidden_classes_excluded_for_non_staff(self):
        """Non-staff users don't see hidden classes."""
        CharacterClassFactory(is_hidden=False)
        CharacterClassFactory(is_hidden=True)
        response = self.client.get("/api/classes/classes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_hidden_classes_visible_for_staff(self):
        """Staff users see hidden classes."""
        CharacterClassFactory(is_hidden=False)
        CharacterClassFactory(is_hidden=True)
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/classes/classes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_filter_by_minimum_level(self):
        """Can filter classes by minimum_level."""
        CharacterClassFactory(minimum_level=1)
        CharacterClassFactory(minimum_level=5)
        response = self.client.get("/api/classes/classes/?minimum_level=1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_retrieve_with_core_traits(self):
        """Retrieve endpoint includes core trait ids."""
        cc = CharacterClassFactory()
        response = self.client.get(f"/api/classes/classes/{cc.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("core_trait_ids", response.data)


class AspectViewSetTests(ClassesAPITestCase):
    """Tests for AspectViewSet."""

    def test_list_aspects(self):
        """List endpoint returns aspects."""
        aspect = AspectFactory()
        response = self.client.get("/api/classes/aspects/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], aspect.name)

    def test_retrieve_aspect(self):
        """Retrieve endpoint returns aspect detail."""
        aspect = AspectFactory()
        response = self.client.get(f"/api/classes/aspects/{aspect.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], aspect.name)
        self.assertEqual(response.data["description"], aspect.description)
