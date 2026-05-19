"""Tests for mechanics API endpoints."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.mechanics.factories import (
    ChallengeCategoryFactory,
    ChallengeInstanceFactory,
    ChallengeTemplateFactory,
    SituationInstanceFactory,
    SituationTemplateFactory,
)


class ChallengeTemplateViewSetTests(TestCase):
    """Tests for ChallengeTemplateViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data shared across all tests in this class."""
        cls.user = AccountFactory()
        cls.category = ChallengeCategoryFactory(name="ApiTestCategory")
        cls.template = ChallengeTemplateFactory(
            name="ApiTestTemplate",
            category=cls.category,
            description_template="A test challenge description",
            goal="Defeat the enemy",
        )
        cls.other_category = ChallengeCategoryFactory(name="ApiOtherCategory")
        cls.other_template = ChallengeTemplateFactory(
            name="ApiOtherTemplate",
            category=cls.other_category,
        )

    def setUp(self):
        """Set up test client for each test."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_challenge_templates(self):
        """Authenticated users can list challenge templates."""
        response = self.client.get("/api/mechanics/challenge-templates/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        names = [t["name"] for t in results]
        assert "ApiTestTemplate" in names
        assert "ApiOtherTemplate" in names

    def test_detail_challenge_template(self):
        """Detail view includes category_name, description_template, and goal."""
        response = self.client.get(f"/api/mechanics/challenge-templates/{self.template.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["category_name"] == "ApiTestCategory"
        assert response.data["description_template"] == "A test challenge description"
        assert response.data["goal"] == "Defeat the enemy"

    def test_filter_by_category(self):
        """Can filter challenge templates by category name (case-insensitive)."""
        response = self.client.get("/api/mechanics/challenge-templates/?category=apitestcategory")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        names = [t["name"] for t in results]
        assert "ApiTestTemplate" in names
        assert "ApiOtherTemplate" not in names

    def test_unauthenticated_returns_401(self):
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/mechanics/challenge-templates/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


class ChallengeInstanceViewSetTests(TestCase):
    """Tests for ChallengeInstanceViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data shared across all tests in this class."""
        cls.user = AccountFactory()
        cls.location = ObjectDBFactory()
        cls.other_location = ObjectDBFactory()
        cls.target = ObjectDBFactory()
        cls.template = ChallengeTemplateFactory(name="InstanceTestTemplate")
        cls.active_instance = ChallengeInstanceFactory(
            template=cls.template,
            location=cls.location,
            target_object=cls.target,
            is_active=True,
        )
        cls.inactive_instance = ChallengeInstanceFactory(
            template=cls.template,
            location=cls.other_location,
            target_object=cls.target,
            is_active=False,
        )

    def setUp(self):
        """Set up test client for each test."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_challenge_instances(self):
        """Authenticated users can list challenge instances."""
        response = self.client.get("/api/mechanics/challenge-instances/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        ids = [r["id"] for r in results]
        assert self.active_instance.id in ids
        assert self.inactive_instance.id in ids

    def test_detail_includes_names(self):
        """Detail view includes template_name, location_name, and target_object_name."""
        response = self.client.get(f"/api/mechanics/challenge-instances/{self.active_instance.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["template_name"] == "InstanceTestTemplate"
        assert response.data["location_name"] == self.location.db_key
        assert response.data["target_object_name"] == self.target.db_key

    def test_filter_by_location(self):
        """Can filter challenge instances by location pk."""
        response = self.client.get(
            f"/api/mechanics/challenge-instances/?location={self.location.pk}"
        )
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        ids = [r["id"] for r in results]
        assert self.active_instance.id in ids
        assert self.inactive_instance.id not in ids

    def test_filter_by_is_active(self):
        """Can filter challenge instances by active status."""
        response = self.client.get("/api/mechanics/challenge-instances/?is_active=true")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        ids = [r["id"] for r in results]
        assert self.active_instance.id in ids
        assert self.inactive_instance.id not in ids

        response = self.client.get("/api/mechanics/challenge-instances/?is_active=false")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        ids = [r["id"] for r in results]
        assert self.inactive_instance.id in ids
        assert self.active_instance.id not in ids


class SituationTemplateViewSetTests(TestCase):
    """Tests for SituationTemplateViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data shared across all tests in this class."""
        cls.user = AccountFactory()
        cls.category = ChallengeCategoryFactory(name="SitTemplateCategory")
        cls.template = SituationTemplateFactory(
            name="ApiSituationTemplate",
            category=cls.category,
            description_template="A situation template description",
        )

    def setUp(self):
        """Set up test client for each test."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_situation_templates(self):
        """Authenticated users can list situation templates."""
        response = self.client.get("/api/mechanics/situation-templates/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        names = [t["name"] for t in results]
        assert "ApiSituationTemplate" in names

    def test_detail_situation_template(self):
        """Detail view includes description_template."""
        response = self.client.get(f"/api/mechanics/situation-templates/{self.template.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["description_template"] == "A situation template description"
        assert response.data["category_name"] == "SitTemplateCategory"


class SituationInstanceViewSetTests(TestCase):
    """Tests for SituationInstanceViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data shared across all tests in this class."""
        cls.user = AccountFactory()
        cls.location = ObjectDBFactory()
        cls.template = SituationTemplateFactory(name="SitInstanceTemplate")
        cls.active_instance = SituationInstanceFactory(
            template=cls.template,
            location=cls.location,
            is_active=True,
        )
        cls.inactive_instance = SituationInstanceFactory(
            template=cls.template,
            location=cls.location,
            is_active=False,
        )

    def setUp(self):
        """Set up test client for each test."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_situation_instances(self):
        """Authenticated users can list situation instances."""
        response = self.client.get("/api/mechanics/situation-instances/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        ids = [r["id"] for r in results]
        assert self.active_instance.id in ids
        assert self.inactive_instance.id in ids

    def test_filter_by_is_active(self):
        """Can filter situation instances by active status."""
        response = self.client.get("/api/mechanics/situation-instances/?is_active=true")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        ids = [r["id"] for r in results]
        assert self.active_instance.id in ids
        assert self.inactive_instance.id not in ids
