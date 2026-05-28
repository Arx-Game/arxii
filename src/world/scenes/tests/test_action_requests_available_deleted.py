"""Verifies that the deprecated /api/action-requests/available/ endpoint is gone.

The merged-availability surface now lives at
/api/actions/characters/<id>/available/ (PlayerActionSerializer). The old
scenes-only endpoint that returned AvailableSceneActions has been removed.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory


class ActionRequestsAvailableEndpointDeletedTests(APITestCase):
    """The GET /api/action-requests/available/ endpoint must return 404."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_old_endpoint_returns_404(self) -> None:
        response = self.client.get("/api/action-requests/available/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
