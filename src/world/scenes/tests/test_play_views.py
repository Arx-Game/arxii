"""Tests for the additive narrative play reader contracts."""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory


class PlayReaderContractTests(APITestCase):
    def test_reader_endpoints_require_authentication(self):
        for path in (
            "/api/play/conversations/",
            "/api/play/poses/",
            "/api/play/context/?id=1",
            "/api/play/search/?q=pose",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, path)

    def test_search_rejects_short_queries_before_database_access(self):
        self.client.force_authenticate(user=AccountFactory())
        response = self.client.get("/api/play/search/?q=x")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("between 2 and 200", response.json()["detail"])

    def test_context_missing_reference_has_non_leaking_response(self):
        self.client.force_authenticate(user=AccountFactory())
        response = self.client.get("/api/play/context/?id=999999")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()["detail"], "This pose is no longer available.")
