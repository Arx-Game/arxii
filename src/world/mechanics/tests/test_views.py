"""Tests for mechanics API views."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import CharacterFactory
from world.mechanics.factories import (
    CharacterModifierFactory,
    ModifierCategoryFactory,
    ModifierTypeFactory,
)


class ModifierCategoryViewSetTests(TestCase):
    """Tests for ModifierCategoryViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="testuser", password="testpass")
        cls.category1 = ModifierCategoryFactory(name="TestStat", display_order=1)
        cls.category2 = ModifierCategoryFactory(name="TestMagic", display_order=2)

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_categories_authenticated(self):
        """Authenticated users can list categories."""
        response = self.client.get("/api/mechanics/categories/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 2
        names = [c["name"] for c in response.data]
        assert "TestStat" in names
        assert "TestMagic" in names

    def test_list_categories_unauthenticated(self):
        """Unauthenticated users cannot list categories."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/mechanics/categories/")
        # DRF returns 403 for unauthenticated requests with SessionAuthentication
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_retrieve_category(self):
        """Can retrieve a single category."""
        response = self.client.get(f"/api/mechanics/categories/{self.category1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "TestStat"
        assert response.data["display_order"] == 1

    def test_categories_are_read_only(self):
        """Viewset is read-only; POST should fail."""
        response = self.client.post(
            "/api/mechanics/categories/",
            {"name": "NewCategory", "display_order": 99},
            format="json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class ModifierTypeViewSetTests(TestCase):
    """Tests for ModifierTypeViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="testuser", password="testpass")
        cls.category1 = ModifierCategoryFactory(name="TypeTestCategory1")
        cls.category2 = ModifierCategoryFactory(name="TypeTestCategory2")
        cls.type1 = ModifierTypeFactory(name="TypeA", category=cls.category1, is_active=True)
        cls.type2 = ModifierTypeFactory(name="TypeB", category=cls.category1, is_active=True)
        cls.type3 = ModifierTypeFactory(name="TypeC", category=cls.category2, is_active=True)
        cls.inactive_type = ModifierTypeFactory(
            name="InactiveType", category=cls.category1, is_active=False
        )

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_types_authenticated(self):
        """Authenticated users can list modifier types."""
        response = self.client.get("/api/mechanics/types/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 3
        names = [t["name"] for t in response.data]
        assert "TypeA" in names
        assert "TypeB" in names
        assert "TypeC" in names

    def test_list_excludes_inactive(self):
        """Inactive modifier types are not listed."""
        response = self.client.get("/api/mechanics/types/")
        names = [t["name"] for t in response.data]
        assert "InactiveType" not in names

    def test_list_types_unauthenticated(self):
        """Unauthenticated users cannot list types."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/mechanics/types/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_filter_by_category(self):
        """Can filter modifier types by category name."""
        response = self.client.get(f"/api/mechanics/types/?category={self.category1.name}")
        assert response.status_code == status.HTTP_200_OK
        # Should have TypeA, TypeB but not TypeC (different category)
        names = [t["name"] for t in response.data]
        assert "TypeA" in names
        assert "TypeB" in names
        assert "TypeC" not in names

    def test_filter_by_is_active(self):
        """Can filter by is_active status."""
        # First make inactive type visible by adding it to queryset
        # Note: The viewset filters is_active=True by default, so we test the filter
        response = self.client.get("/api/mechanics/types/?is_active=true")
        assert response.status_code == status.HTTP_200_OK
        names = [t["name"] for t in response.data]
        assert "InactiveType" not in names

    def test_retrieve_type(self):
        """Can retrieve a single modifier type."""
        response = self.client.get(f"/api/mechanics/types/{self.type1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "TypeA"
        assert response.data["category_name"] == "TypeTestCategory1"

    def test_types_are_read_only(self):
        """Viewset is read-only; POST should fail."""
        response = self.client.post(
            "/api/mechanics/types/",
            {"name": "NewType", "category": self.category1.id},
            format="json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class CharacterModifierViewSetTests(TestCase):
    """Tests for CharacterModifierViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="testuser", password="testpass")
        cls.character1 = CharacterFactory()
        cls.character2 = CharacterFactory()
        cls.category = ModifierCategoryFactory(name="ModTestCategory")
        cls.modifier_type1 = ModifierTypeFactory(name="ModType1", category=cls.category)
        cls.modifier_type2 = ModifierTypeFactory(name="ModType2", category=cls.category)

        cls.modifier1 = CharacterModifierFactory(
            character=cls.character1, modifier_type=cls.modifier_type1, value=10
        )
        cls.modifier2 = CharacterModifierFactory(
            character=cls.character1, modifier_type=cls.modifier_type2, value=-5
        )
        cls.modifier3 = CharacterModifierFactory(
            character=cls.character2, modifier_type=cls.modifier_type1, value=20
        )

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _get_results(self, response_data):
        """Extract results from paginated or non-paginated response."""
        if isinstance(response_data, dict) and "results" in response_data:
            return response_data["results"]
        return response_data

    def test_list_modifiers_authenticated(self):
        """Authenticated users can list character modifiers."""
        response = self.client.get("/api/mechanics/character-modifiers/")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        assert len(data) >= 3

    def test_list_modifiers_unauthenticated(self):
        """Unauthenticated users cannot list modifiers."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/mechanics/character-modifiers/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_filter_by_character(self):
        """Can filter modifiers by character."""
        response = self.client.get(
            f"/api/mechanics/character-modifiers/?character={self.character1.id}"
        )
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        # Should only have modifiers for character1 (we created 2)
        assert len(data) == 2
        for mod in data:
            assert mod["character"] == self.character1.id

    def test_filter_by_modifier_type(self):
        """Can filter modifiers by modifier_type."""
        response = self.client.get(
            f"/api/mechanics/character-modifiers/?modifier_type={self.modifier_type1.id}"
        )
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        # Should only have modifiers of type modifier_type1 (we created 2)
        assert len(data) == 2
        for mod in data:
            assert mod["modifier_type"] == self.modifier_type1.id

    def test_retrieve_modifier(self):
        """Can retrieve a single modifier."""
        response = self.client.get(f"/api/mechanics/character-modifiers/{self.modifier1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["value"] == 10
        assert response.data["modifier_type_name"] == "ModType1"
        assert response.data["category_name"] == "ModTestCategory"

    def test_modifiers_are_read_only(self):
        """Viewset is read-only; POST should fail."""
        response = self.client.post(
            "/api/mechanics/character-modifiers/",
            {
                "character": self.character1.id,
                "modifier_type": self.modifier_type1.id,
                "value": 15,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_serializer_includes_source_fields(self):
        """Serializer includes source_type and source_id fields."""
        response = self.client.get(f"/api/mechanics/character-modifiers/{self.modifier1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert "source_type" in response.data
        assert "source_id" in response.data
        # Since no source was set, these should be null
        assert response.data["source_type"] is None
        assert response.data["source_id"] is None
