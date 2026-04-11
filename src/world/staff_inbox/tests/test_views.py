"""Tests for staff_inbox API endpoints."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.player_submissions.factories import PlayerFeedbackFactory


class StaffInboxViewPermissionTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="inboxstaff1", is_staff=True)
        cls.regular = AccountFactory(username="inboxregular1")
        PlayerFeedbackFactory.create_batch(3)

    def test_unauthenticated_denied(self) -> None:
        client = APIClient()
        response = client.get("/api/staff-inbox/")
        self.assertIn(response.status_code, (401, 403))

    def test_regular_user_denied(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.regular)
        response = client.get("/api/staff-inbox/")
        self.assertEqual(response.status_code, 403)

    def test_staff_can_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.get("/api/staff-inbox/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

    def test_category_filter(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.get(
            "/api/staff-inbox/?categories=player_feedback",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

    def test_invalid_category_returns_400(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.get(
            "/api/staff-inbox/?categories=not_a_real_category",
        )
        self.assertEqual(response.status_code, 400)

    def test_pagination_params(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.get("/api/staff-inbox/?page=1&page_size=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["current_page"], 1)
        self.assertEqual(response.data["page_size"], 2)
        self.assertEqual(response.data["num_pages"], 2)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_pagination_shape_matches_standard(self) -> None:
        """Response shape matches StandardResultsSetPagination."""
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.get("/api/staff-inbox/")
        self.assertEqual(response.status_code, 200)
        expected_keys = {
            "count",
            "next",
            "previous",
            "page_size",
            "num_pages",
            "current_page",
            "results",
        }
        self.assertEqual(set(response.data.keys()), expected_keys)


class AccountHistoryViewPermissionTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="inboxstaff2", is_staff=True)
        cls.regular = AccountFactory(username="inboxregular2")

    def test_regular_user_denied(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.regular)
        response = client.get(
            f"/api/staff-inbox/accounts/{self.regular.pk}/history/",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_can_retrieve(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.get(
            f"/api/staff-inbox/accounts/{self.regular.pk}/history/",
        )
        self.assertEqual(response.status_code, 200)
