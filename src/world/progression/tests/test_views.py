"""
Tests for progression API views.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.progression.factories import KudosClaimCategoryFactory, KudosSourceCategoryFactory
from world.progression.services import award_kudos


class ProgressionViewTestCase(TestCase):
    """Base test case with authenticated API client."""

    @classmethod
    def setUpTestData(cls):
        from evennia.accounts.models import AccountDB

        cls.user = AccountDB.objects.create_user(
            username="testuser",
            email="test@test.com",
            password="testpass123",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class AccountProgressionViewTests(ProgressionViewTestCase):
    """Tests for GET /api/progression/account/."""

    def test_get_progression_data(self):
        """Returns progression data for authenticated user."""
        response = self.client.get("/api/progression/account/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("xp", response.data)
        self.assertIn("kudos", response.data)
        self.assertIn("claim_categories", response.data)

    def test_unauthenticated_denied(self):
        """Unauthenticated requests are denied."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/progression/account/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ClaimKudosViewTests(ProgressionViewTestCase):
    """Tests for POST /api/progression/claim-kudos/."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.source_category = KudosSourceCategoryFactory(name="test_source")
        cls.claim_category = KudosClaimCategoryFactory(
            name="xp_convert", kudos_cost=1, reward_amount=1
        )

    def _seed_kudos(self, amount: int) -> None:
        award_kudos(
            account=self.user,
            amount=amount,
            source_category=self.source_category,
            description="Seed",
        )

    def test_claim_kudos_for_xp(self):
        """Successfully converts kudos to XP and returns updated data."""
        self._seed_kudos(50)
        response = self.client.post(
            "/api/progression/claim-kudos/",
            {"claim_category_id": self.claim_category.id, "amount": 30},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["kudos"]["current_available"], 20)
        self.assertEqual(response.data["xp"]["current_available"], 30)

    def test_insufficient_kudos(self):
        """Returns 400 when claiming more than available."""
        self._seed_kudos(10)
        response = self.client.post(
            "/api/progression/claim-kudos/",
            {"claim_category_id": self.claim_category.id, "amount": 50},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Insufficient kudos for this conversion.")

    def test_missing_fields(self):
        """Returns 400 when required fields are missing."""
        response = self.client.post(
            "/api/progression/claim-kudos/",
            {"amount": 10},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_category(self):
        """Returns 400 for nonexistent claim category."""
        self._seed_kudos(10)
        response = self.client.post(
            "/api/progression/claim-kudos/",
            {"claim_category_id": 99999, "amount": 10},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_category_rejected(self):
        """Returns 400 for inactive claim category."""
        inactive = KudosClaimCategoryFactory(name="inactive", is_active=False)
        self._seed_kudos(10)
        response = self.client.post(
            "/api/progression/claim-kudos/",
            {"claim_category_id": inactive.id, "amount": 10},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_reward_rejected(self):
        """Returns 400 when conversion yields zero XP."""
        expensive = KudosClaimCategoryFactory(name="expensive", kudos_cost=100, reward_amount=1)
        self._seed_kudos(50)
        response = self.client.post(
            "/api/progression/claim-kudos/",
            {"claim_category_id": expensive.id, "amount": 50},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_denied(self):
        """Unauthenticated requests are denied."""
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/progression/claim-kudos/",
            {"claim_category_id": self.claim_category.id, "amount": 10},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
