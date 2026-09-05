"""Escalation curve catalog endpoint for the GM settings picker (#3552)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.combat.factories import EscalationCurveFactory
from world.gm.factories import GMProfileFactory


class EscalationCurveCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.slow = EscalationCurveFactory(name="Slow Burn", start_round=3)
        cls.fast = EscalationCurveFactory(name="Flashpoint", start_round=1)
        cls.staff = AccountFactory(username="curve_staff", is_staff=True)
        cls.gm = AccountFactory(username="curve_gm")
        GMProfileFactory(account=cls.gm)
        cls.player = AccountFactory(username="curve_player")

    def _client(self, account: AccountFactory) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=account)
        return client

    def test_gm_lists_curves_by_name(self) -> None:
        response = self._client(self.gm).get("/api/combat/escalation-curves/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [row["name"] for row in response.data["results"]]
        self.assertEqual(names, ["Flashpoint", "Slow Burn"])
        self.assertEqual(response.data["results"][0]["start_round"], 1)
        self.assertIn("description", response.data["results"][0])

    def test_staff_lists_curves(self) -> None:
        response = self._client(self.staff).get("/api/combat/escalation-curves/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_search_filters_by_name(self) -> None:
        response = self._client(self.gm).get("/api/combat/escalation-curves/?search=slow")
        self.assertEqual([r["name"] for r in response.data["results"]], ["Slow Burn"])

    def test_player_is_forbidden(self) -> None:
        response = self._client(self.player).get("/api/combat/escalation-curves/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
