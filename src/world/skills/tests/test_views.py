"""
Tests for Skills API views.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.skills.factories import (
    PathSkillSuggestionFactory,
    SkillFactory,
    SkillPointBudgetFactory,
    SpecializationFactory,
)
from world.skills.models import SkillPointBudget


class SkillAPITestCase(TestCase):
    """Base test case with authenticated API client."""

    @classmethod
    def setUpTestData(cls):
        from evennia.accounts.models import AccountDB

        # Create a test user
        cls.user = AccountDB.objects.create_user(
            username="testuser",
            email="test@test.com",
            password="testpass123",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class SkillViewSetTests(SkillAPITestCase):
    """Tests for SkillViewSet."""

    def test_list_skills(self):
        """List endpoint returns skills."""
        skill = SkillFactory()
        response = self.client.get("/api/skills/skills/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], skill.name)

    def test_list_skills_only_active(self):
        """List endpoint only returns active skills by default."""
        SkillFactory(is_active=True)
        SkillFactory(is_active=False)
        response = self.client.get("/api/skills/skills/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_retrieve_skill_with_specializations(self):
        """Retrieve endpoint returns skill with specializations."""
        skill = SkillFactory()
        spec = SpecializationFactory(parent_skill=skill)

        response = self.client.get(f"/api/skills/skills/{skill.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], skill.name)
        self.assertEqual(len(response.data["specializations"]), 1)
        self.assertEqual(response.data["specializations"][0]["name"], spec.name)

    def test_with_specializations_action(self):
        """with_specializations action returns all skills with specializations."""
        skill = SkillFactory()
        SpecializationFactory(parent_skill=skill)

        response = self.client.get("/api/skills/skills/with_specializations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertIn("specializations", response.data[0])


class SpecializationViewSetTests(SkillAPITestCase):
    """Tests for SpecializationViewSet."""

    def test_list_specializations(self):
        """List endpoint returns specializations."""
        spec = SpecializationFactory()
        response = self.client.get("/api/skills/specializations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], spec.name)

    def test_filter_by_parent_skill(self):
        """Can filter specializations by parent skill."""
        skill1 = SkillFactory()
        skill2 = SkillFactory()
        SpecializationFactory(parent_skill=skill1)
        SpecializationFactory(parent_skill=skill2)

        response = self.client.get(f"/api/skills/specializations/?parent_skill={skill1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class PathSkillSuggestionViewSetTests(SkillAPITestCase):
    """Tests for PathSkillSuggestionViewSet."""

    def test_list_suggestions(self):
        """List endpoint returns path skill suggestions."""
        suggestion = PathSkillSuggestionFactory()
        response = self.client.get("/api/skills/path-skill-suggestions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["suggested_value"], suggestion.suggested_value)


class SkillPointBudgetViewSetTests(SkillAPITestCase):
    """Tests for SkillPointBudgetViewSet."""

    def test_list_returns_single_budget(self):
        """List endpoint returns single budget object, not array."""
        SkillPointBudgetFactory()
        response = self.client.get("/api/skills/skill-budget/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should be a single object, not an array
        self.assertIn("path_points", response.data)
        self.assertIn("free_points", response.data)
        self.assertIn("total_points", response.data)

    def test_budget_defaults_created_automatically(self):
        """Budget is created with defaults if none exists."""
        SkillPointBudget.objects.all().delete()
        response = self.client.get("/api/skills/skill-budget/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["path_points"], 50)
        self.assertEqual(response.data["free_points"], 60)
        self.assertEqual(response.data["total_points"], 110)
