"""Tests for the superuser-only 'Game Setup' hub view (#1333)."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.seeds.tests.content_stub import stub_content_root


class TestGameSetupView(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_non_superuser_is_denied(self) -> None:
        """Staff (non-superuser) is blocked from the Game Setup hub."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_game_setup"))
        self.assertIn(resp.status_code, (403, 302))  # 302 = redirect-to-login also acceptable

    @stub_content_root()
    def test_superuser_sees_hub_inventory_and_links(self) -> None:
        """Superuser sees the welcome copy, the Big Button, and the per-cluster inventory."""
        from world.seeds.database import seed_dev_database

        self.client.force_login(self.super)
        # Seed a little so the inventory shows non-zero counts.
        seed_dev_database()
        resp = self.client.get(reverse("admin_game_setup"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # Wayfinding / welcome copy.
        self.assertIn("Welcome to a new Arx-based instance", body)
        # The Big Button link is surfaced.
        self.assertIn("Load sane defaults", body)
        # The export link is surfaced.
        self.assertIn("Export Data", body)
        # The inventory surfaces a seeded cluster (by name) and its representative content.
        self.assertIn("character_creation", body)
