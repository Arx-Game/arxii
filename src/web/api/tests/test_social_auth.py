"""Tests for social authentication endpoints."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


class SocialProvidersAPITestCase(TestCase):
    """Test cases for the social providers endpoint."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = APIClient()
        self.url = "/api/social-providers/"

    def test_returns_providers_list(self):
        """Test that endpoint returns a list of providers."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("providers", response.data)
        self.assertIsInstance(response.data["providers"], list)

    def test_endpoint_is_publicly_accessible(self):
        """Test that the social providers endpoint doesn't require authentication."""
        response = self.client.get(self.url)

        # Should not return 401/403
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_provider_structure(self):
        """Test that returned providers have correct structure."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Each provider should have 'id' and 'name' keys if any are returned
        for provider in response.data["providers"]:
            self.assertIn("id", provider)
            self.assertIn("name", provider)
