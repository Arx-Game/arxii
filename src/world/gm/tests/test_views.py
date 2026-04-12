"""Tests for GM system views."""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMApplicationStatus
from world.gm.factories import GMApplicationFactory


class GMApplicationCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_authenticated_user_can_create(self) -> None:
        url = reverse("gm:gm-application-list")
        resp = self.client.post(url, {"application_text": "I want to GM!"}, format="json")
        assert resp.status_code == 201
        assert resp.data["application_text"] == "I want to GM!"

    def test_unauthenticated_cannot_create(self) -> None:
        self.client.force_authenticate(user=None)
        url = reverse("gm:gm-application-list")
        resp = self.client.post(url, {"application_text": "test"}, format="json")
        assert resp.status_code in (401, 403)


class GMApplicationStaffTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_superuser=True)
        cls.user = AccountFactory()
        cls.application = GMApplicationFactory()

    def setUp(self) -> None:
        self.client = APIClient()

    def test_staff_can_list(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-application-list")
        resp = self.client.get(url)
        assert resp.status_code == 200

    def test_non_staff_cannot_list(self) -> None:
        self.client.force_authenticate(user=self.user)
        url = reverse("gm:gm-application-list")
        resp = self.client.get(url)
        assert resp.status_code == 403

    def test_staff_can_update_status(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-application-detail", args=[self.application.pk])
        resp = self.client.patch(
            url,
            {
                "status": GMApplicationStatus.APPROVED,
                "staff_response": "Welcome!",
            },
            format="json",
        )
        assert resp.status_code == 200
        self.application.refresh_from_db()
        assert self.application.status == GMApplicationStatus.APPROVED

    def test_status_filter(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-application-list")
        resp = self.client.get(url, {"status": "pending"})
        assert resp.status_code == 200
