"""Tests for the `set_reactive_triggers` staff wiring action (#3417 task 7).

Verifies ``PATCH /api/conditions/templates/{id}/set_reactive_triggers/`` lets
staff replace (set semantics, not add) the TriggerDefinitions installed when a
ConditionTemplate is applied, while non-staff and malformed requests are
rejected.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from flows.factories import TriggerDefinitionFactory
from world.conditions.factories import ConditionTemplateFactory
from world.gm.factories import GMProfileFactory


class SetReactiveTriggersTests(TestCase):
    """Tests for ConditionTemplateViewSet.set_reactive_triggers."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory(is_staff=False)
        cls.template = ConditionTemplateFactory()
        cls.trigger_a = TriggerDefinitionFactory()
        cls.trigger_b = TriggerDefinitionFactory()
        cls.trigger_c = TriggerDefinitionFactory()

    def setUp(self) -> None:
        self.client = APIClient()

    def _url(self, template_id: int) -> str:
        return f"/api/conditions/templates/{template_id}/set_reactive_triggers/"

    def test_staff_sets_two_trigger_definitions(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(
            self._url(self.template.id),
            {"trigger_definition_ids": [self.trigger_a.id, self.trigger_b.id]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert set(response.data["trigger_definition_ids"]) == {
            self.trigger_a.id,
            self.trigger_b.id,
        }
        self.template.refresh_from_db()
        assert self.template.reactive_triggers.count() == 2
        assert set(self.template.reactive_triggers.values_list("id", flat=True)) == {
            self.trigger_a.id,
            self.trigger_b.id,
        }

    def test_replacing_existing_set_uses_set_semantics(self) -> None:
        self.template.reactive_triggers.set([self.trigger_a])
        self.client.force_authenticate(user=self.staff)

        response = self.client.patch(
            self._url(self.template.id),
            {"trigger_definition_ids": [self.trigger_b.id, self.trigger_c.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        self.template.refresh_from_db()
        ids = set(self.template.reactive_triggers.values_list("id", flat=True))
        assert ids == {self.trigger_b.id, self.trigger_c.id}
        assert self.trigger_a.id not in ids

    def test_non_staff_forbidden(self) -> None:
        self.client.force_authenticate(user=self.player)
        response = self.client.patch(
            self._url(self.template.id),
            {"trigger_definition_ids": [self.trigger_a.id]},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_bogus_trigger_id_returns_400(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(
            self._url(self.template.id),
            {"trigger_definition_ids": [999999999]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        self.template.refresh_from_db()
        assert self.template.reactive_triggers.count() == 0

    def test_non_list_body_returns_400(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(
            self._url(self.template.id),
            {"trigger_definition_ids": "not-a-list"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class ReactiveTriggerIdsFieldGatingTests(TestCase):
    """`reactive_trigger_ids` on ConditionTemplateSerializer is GM/staff-only.

    ``ConditionTemplateViewSet`` is deliberately player-facing
    (``IsAuthenticated`` -- TechniqueBuilderPage reads it), but the #3417
    spec's leak-analysis table commits to no player-facing serializer
    exposing flow wiring metadata. The field must gate to `[]` for a plain
    authenticated player even when the template has triggers wired, while
    staff and GM-profile accounts see the real ids.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory(is_staff=False)
        cls.gm_account = AccountFactory(is_staff=False)
        GMProfileFactory(account=cls.gm_account)
        cls.template = ConditionTemplateFactory()
        cls.trigger_a = TriggerDefinitionFactory()
        cls.trigger_b = TriggerDefinitionFactory()
        cls.template.reactive_triggers.set([cls.trigger_a, cls.trigger_b])

    def setUp(self) -> None:
        self.client = APIClient()

    def _list_url(self) -> str:
        return "/api/conditions/templates/"

    def _detail_url(self, template_id: int) -> str:
        return f"/api/conditions/templates/{template_id}/"

    def _wired_row(self, response) -> dict:
        return next(row for row in response.data if row["id"] == self.template.id)

    def test_plain_player_sees_empty_list_even_when_wired(self) -> None:
        self.client.force_authenticate(user=self.player)
        response = self.client.get(self._list_url())
        assert response.status_code == status.HTTP_200_OK, response.data
        assert self._wired_row(response)["reactive_trigger_ids"] == []

    def test_plain_player_sees_empty_on_detail_too(self) -> None:
        self.client.force_authenticate(user=self.player)
        response = self.client.get(self._detail_url(self.template.id))
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["reactive_trigger_ids"] == []

    def test_staff_sees_real_ids(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(self._list_url())
        assert response.status_code == status.HTTP_200_OK, response.data
        assert set(self._wired_row(response)["reactive_trigger_ids"]) == {
            self.trigger_a.id,
            self.trigger_b.id,
        }

    def test_gm_profile_non_staff_sees_real_ids(self) -> None:
        self.client.force_authenticate(user=self.gm_account)
        response = self.client.get(self._list_url())
        assert response.status_code == status.HTTP_200_OK, response.data
        assert set(self._wired_row(response)["reactive_trigger_ids"]) == {
            self.trigger_a.id,
            self.trigger_b.id,
        }
