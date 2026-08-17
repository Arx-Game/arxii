"""Tests for the public downtime endpoint (#3194)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from world.downtime.factories import DowntimeWindowFactory


class NextDowntimeViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/downtime/next/"

    def test_anonymous_get_with_no_downtime(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["downtime"])

    def test_upcoming_window_shape(self):
        window = DowntimeWindowFactory(
            starts_at=timezone.now() + timedelta(hours=3),
            expected_duration_minutes=45,
            message="Database maintenance",
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data["downtime"]
        self.assertEqual(payload["source"], "staff")
        self.assertEqual(payload["expected_duration_minutes"], 45)
        self.assertEqual(payload["message"], "Database maintenance")
        self.assertIn(str(window.starts_at.year), payload["starts_at"])
