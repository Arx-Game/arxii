"""Tests for ActionTemplate API endpoints."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from actions.constants import ActionTargetType
from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory


class ActionTemplateViewSetTests(APITestCase):
    """Tests for the ActionTemplate read-only ViewSet."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.template_self = ActionTemplateFactory(
            name="Meditate",
            target_type=ActionTargetType.SELF,
        )
        cls.template_single = ActionTemplateFactory(
            name="Fire Bolt",
            target_type=ActionTargetType.SINGLE,
        )
        cls.template_area = ActionTemplateFactory(
            name="Earthquake",
            target_type=ActionTargetType.AREA,
        )
        cls.template_filtered = ActionTemplateFactory(
            name="Mass Heal",
            target_type=ActionTargetType.FILTERED_GROUP,
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_list_returns_templates(self) -> None:
        url = reverse("actiontemplate-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 4

    def test_unauthenticated_returns_403(self) -> None:
        self.client.force_authenticate(user=None)
        url = reverse("actiontemplate-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_filter_by_target_type(self) -> None:
        url = reverse("actiontemplate-list")
        response = self.client.get(url, {"target_type": ActionTargetType.SINGLE})
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Fire Bolt"

    def test_requires_target_true_for_single(self) -> None:
        url = reverse("actiontemplate-detail", kwargs={"pk": self.template_single.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["requires_target"] is True

    def test_requires_target_true_for_filtered_group(self) -> None:
        url = reverse("actiontemplate-detail", kwargs={"pk": self.template_filtered.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["requires_target"] is True

    def test_requires_target_false_for_self(self) -> None:
        url = reverse("actiontemplate-detail", kwargs={"pk": self.template_self.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["requires_target"] is False

    def test_requires_target_false_for_area(self) -> None:
        url = reverse("actiontemplate-detail", kwargs={"pk": self.template_area.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["requires_target"] is False

    def test_retrieve_single_template(self) -> None:
        url = reverse("actiontemplate-detail", kwargs={"pk": self.template_self.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Meditate"
        assert response.data["target_type"] == ActionTargetType.SELF
