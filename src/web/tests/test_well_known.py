"""Tests for standards-based ``/.well-known`` endpoints."""

from datetime import datetime

from django.test import TestCase
from django.urls import reverse


class WellKnownEndpointTests(TestCase):
    """Keep password-manager and vulnerability-reporting discovery endpoints stable."""

    def test_change_password_redirects_without_authentication(self):
        """Password managers can discover the existing authenticated form."""
        response = self.client.get(reverse("well-known-change-password"))

        assert response.status_code == 302
        assert response["Location"] == "/profile/account"

    def test_change_password_endpoint_is_get_only(self):
        """The discovery URL must not mutate account state itself."""
        response = self.client.post(reverse("well-known-change-password"))

        assert response.status_code == 405

    def test_change_password_supports_head(self):
        """HTTP clients may probe the discovery endpoint with HEAD."""
        response = self.client.head(reverse("well-known-change-password"))

        assert response.status_code == 302
        assert response["Location"] == "/profile/account"

    def test_security_txt_publishes_required_fields(self):
        """RFC 9116 requires a contact and an expiry in security.txt."""
        response = self.client.get(reverse("well-known-security"))
        body = response.content.decode()

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/plain")
        assert "Contact: https://github.com/Arx-Game/arxii/security/advisories/new" in body
        expires = next(
            line.removeprefix("Expires: ")
            for line in body.splitlines()
            if line.startswith("Expires: ")
        )
        assert expires.endswith("Z")
        assert datetime.fromisoformat(expires).tzinfo is not None
        assert "Preferred-Languages: en" in body
