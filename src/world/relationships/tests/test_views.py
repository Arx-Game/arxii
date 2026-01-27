"""Tests for relationships API views."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import CharacterFactory
from world.mechanics.factories import ModifierTypeFactory
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipConditionFactory,
)


class RelationshipConditionViewSetTests(TestCase):
    """Tests for RelationshipConditionViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="testuser", password="testpass")
        cls.condition1 = RelationshipConditionFactory(name="Attracted To", display_order=1)
        cls.condition2 = RelationshipConditionFactory(name="Fears", display_order=2)
        cls.condition3 = RelationshipConditionFactory(name="Trusts", display_order=3)

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_conditions_authenticated(self):
        """Authenticated users can list conditions."""
        response = self.client.get("/api/relationships/conditions/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 3
        names = [c["name"] for c in response.data]
        assert "Attracted To" in names
        assert "Fears" in names
        assert "Trusts" in names

    def test_list_conditions_unauthenticated(self):
        """Unauthenticated users cannot list conditions."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/relationships/conditions/")
        # DRF returns 403 for unauthenticated requests with SessionAuthentication
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_list_conditions_no_pagination(self):
        """Conditions endpoint returns all items without pagination."""
        response = self.client.get("/api/relationships/conditions/")
        assert response.status_code == status.HTTP_200_OK
        # Response should be a list, not a paginated dict
        assert isinstance(response.data, list)
        # No 'results' key (would indicate pagination)
        assert not isinstance(response.data, dict)

    def test_retrieve_condition(self):
        """Can retrieve a single condition."""
        response = self.client.get(f"/api/relationships/conditions/{self.condition1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Attracted To"
        assert response.data["display_order"] == 1

    def test_conditions_are_read_only(self):
        """Viewset is read-only; POST should fail."""
        response = self.client.post(
            "/api/relationships/conditions/",
            {"name": "NewCondition", "display_order": 99},
            format="json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_conditions_include_gates_modifiers(self):
        """Conditions include gates_modifiers in response."""
        modifier = ModifierTypeFactory(name="AllureModifier")
        self.condition1.gates_modifiers.add(modifier)

        response = self.client.get(f"/api/relationships/conditions/{self.condition1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert "gates_modifiers" in response.data


class CharacterRelationshipViewSetTests(TestCase):
    """Tests for CharacterRelationshipViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="testuser", password="testpass")
        cls.character1 = CharacterFactory()
        cls.character2 = CharacterFactory()
        cls.character3 = CharacterFactory()

        cls.condition = RelationshipConditionFactory(name="TestCondition")

        # Create relationships
        cls.rel1 = CharacterRelationshipFactory(
            source=cls.character1, target=cls.character2, reputation=100
        )
        cls.rel2 = CharacterRelationshipFactory(
            source=cls.character1, target=cls.character3, reputation=-50
        )
        cls.rel3 = CharacterRelationshipFactory(
            source=cls.character2, target=cls.character1, reputation=200
        )

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_relationships_authenticated(self):
        """Authenticated users can list relationships."""
        response = self.client.get("/api/relationships/relationships/")
        assert response.status_code == status.HTTP_200_OK
        # Handle paginated or non-paginated response
        data = self._get_results(response.data)
        assert len(data) >= 3

    def test_list_relationships_unauthenticated(self):
        """Unauthenticated users cannot list relationships."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/relationships/relationships/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_retrieve_relationship(self):
        """Can retrieve a single relationship."""
        response = self.client.get(f"/api/relationships/relationships/{self.rel1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["reputation"] == 100

    def test_relationships_are_read_only(self):
        """Viewset is read-only; POST should fail."""
        response = self.client.post(
            "/api/relationships/relationships/",
            {
                "source": self.character1.id,
                "target": self.character2.id,
                "reputation": 50,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_filter_by_source(self):
        """Can filter relationships by source."""
        response = self.client.get(f"/api/relationships/relationships/?source={self.character1.id}")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        # character1 is source of rel1 and rel2
        assert len(data) == 2
        for rel in data:
            assert rel["source"] == self.character1.id

    def test_filter_by_target(self):
        """Can filter relationships by target."""
        response = self.client.get(f"/api/relationships/relationships/?target={self.character1.id}")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        # character1 is target of rel3 only
        assert len(data) == 1
        assert data[0]["target"] == self.character1.id

    def test_filter_by_source_and_target(self):
        """Can filter relationships by both source and target."""
        response = self.client.get(
            f"/api/relationships/relationships/"
            f"?source={self.character1.id}&target={self.character2.id}"
        )
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        assert len(data) == 1
        assert data[0]["source"] == self.character1.id
        assert data[0]["target"] == self.character2.id

    def test_relationship_includes_conditions(self):
        """Relationship response includes conditions."""
        self.rel1.conditions.add(self.condition)

        response = self.client.get(f"/api/relationships/relationships/{self.rel1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert "conditions" in response.data

    def _get_results(self, response_data):
        """Extract results from paginated or non-paginated response."""
        if isinstance(response_data, dict) and "results" in response_data:
            return response_data["results"]
        return response_data
