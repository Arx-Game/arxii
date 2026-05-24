"""Tests for GET /api/combat/action-outcome-details/

Phase 9, Task 9.4.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory


class ActionOutcomeDetailsViewTests(APITestCase):
    """GET /api/combat/action-outcome-details/ returns a list of outcome details."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_returns_empty_list_when_no_ids_given(self) -> None:
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_returns_one_row_per_action_id(self) -> None:
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url, {"action_interaction_ids": "10,20"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        ids = {row["action_interaction_id"] for row in response.data}
        assert ids == {10, 20}

    def test_each_row_has_effects_list(self) -> None:
        """v1: effects list is empty (no CombatRoundAction → Interaction bridge yet)."""
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url, {"action_interaction_ids": "5"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        row = response.data[0]
        assert row["action_interaction_id"] == 5
        assert row["effects"] == []

    def test_rejects_non_integer_ids(self) -> None:
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url, {"action_interaction_ids": "abc"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_requires_authentication(self) -> None:
        self.client.force_authenticate(user=None)
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url, {"action_interaction_ids": "1"})
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }


class OutcomeDetailDataShapeTest(TestCase):
    """Unit tests for the _build_outcome_detail helper."""

    def test_returns_correct_shape_for_given_id(self) -> None:
        from world.combat.views_outcome_details import _build_outcome_detail

        detail = _build_outcome_detail(42)
        assert detail.action_interaction_id == 42
        assert detail.effects == []
