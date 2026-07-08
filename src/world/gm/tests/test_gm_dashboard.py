"""Tests for GET /api/gm/dashboard/ — the GM dashboard aggregation (#2004)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory


class GMDashboardViewTest(APITestCase):
    """GET /api/gm/dashboard/ — IsGM-gated dashboard aggregation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gm_account = AccountFactory()
        cls.gm_profile = GMProfileFactory(account=cls.gm_account)
        cls.gm_table = GMTableFactory(gm=cls.gm_profile)
        cls.non_gm_account = AccountFactory()

    def test_gm_can_access_dashboard(self) -> None:
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data
        # All expected sections present.
        for key in [
            "episodes_ready_to_run",
            "pending_agm_claims",
            "assigned_session_requests",
            "waiting_for_gm",
            "my_tables",
            "pending_story_offers",
            "evidence_summary",
        ]:
            self.assertIn(key, data)
        # The GM's table appears in my_tables.
        table_ids = [t["id"] for t in data["my_tables"]]
        self.assertIn(self.gm_table.pk, table_ids)
        # Evidence summary carries the GM's level.
        self.assertEqual(data["evidence_summary"]["level"], self.gm_profile.level)

    def test_non_gm_rejected(self) -> None:
        self.client.force_authenticate(user=self.non_gm_account)
        url = reverse("gm:gm-dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
