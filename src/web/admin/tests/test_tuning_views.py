"""Tests for the superuser-only Game Tuning dashboard skeleton (#1221)."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB


class TestTuningDashboardView(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_anonymous_redirected_to_login(self) -> None:
        """An unauthenticated request is redirected to the admin login page."""
        resp = self.client.get(reverse("admin_tuning"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_non_superuser_forbidden(self) -> None:
        """Staff who are not superusers are blocked (403)."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_tuning"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_gets_dashboard(self) -> None:
        """Superuser sees the dashboard with all four panel stubs."""
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="panel-checks"', body)
        self.assertIn('id="panel-consequences"', body)
        self.assertIn('id="panel-conditions"', body)
        self.assertIn('id="panel-simulation"', body)
