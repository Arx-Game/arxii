"""Tests for the superuser-only Game Ops dashboard views (#1221 Task 7)."""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB


class TestOpsDashboardView(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "opsroot", "opsroot@example.com", "pw-123456"
        )
        cls.staff = AccountDB.objects.create_user("opsstaffer", "os@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_anonymous_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("admin_ops"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_ops"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_gets_dashboard(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_ops"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="panel-ops-progression"', body)
        self.assertIn('id="panel-ops-economy"', body)
        self.assertIn('id="panel-ops-story"', body)
        self.assertIn('id="panel-ops-reports"', body)


class TestOpsFragmentViews(TestCase):
    """Each fragment is superuser-only, mirroring the dashboard's gate."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "opsfragroot", "opsfrag@example.com", "pw-123456"
        )
        cls.staff = AccountDB.objects.create_user("opsfragstaff", "ofs@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_progression_fragment_superuser_200(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_ops_progression"))
        self.assertEqual(resp.status_code, 200)

    def test_economy_fragment_superuser_200(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_ops_economy"))
        self.assertEqual(resp.status_code, 200)

    def test_story_fragment_superuser_200(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_ops_story"))
        self.assertEqual(resp.status_code, 200)

    def test_story_fragment_surfaces_gm_reward_config(self) -> None:
        """GM Story Reward balance knobs (#2123) are readable on this panel."""
        from world.gm.models import GMRewardConfig

        config = GMRewardConfig.load()
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_ops_story"))
        body = resp.content.decode()
        self.assertIn(str(config.beat_xp_per_player), body)
        self.assertIn(str(config.weekly_reward_cap), body)

    def test_reports_fragment_superuser_200(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_ops_reports"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("/staff/feedback", resp.content.decode())
        self.assertIn("/staff/bug-reports", resp.content.decode())
        self.assertIn("/staff/player-reports", resp.content.decode())
        self.assertIn("/staff/system-errors", resp.content.decode())

    def test_staff_non_superuser_forbidden_on_each_fragment(self) -> None:
        self.client.force_login(self.staff)
        for url_name in (
            "admin_ops_progression",
            "admin_ops_economy",
            "admin_ops_story",
            "admin_ops_reports",
        ):
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 403, url_name)
