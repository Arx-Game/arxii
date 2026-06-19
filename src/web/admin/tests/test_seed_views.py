"""Tests for the superuser-only 'Load sane defaults' admin button (#651)."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB


class TestSeedAdminButton(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_run_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("admin_seed_run"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_can_run_and_is_redirected(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.post(reverse("admin_seed_run"))
        self.assertEqual(resp.status_code, 302)
