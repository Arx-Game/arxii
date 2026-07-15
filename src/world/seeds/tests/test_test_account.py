"""Tests for the test-account seed and management command."""

from io import StringIO

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from evennia_extensions.models import PlayerData
from world.seeds.test_account import seed_test_account

User = get_user_model()


class SeedTestAccountTests(TestCase):
    """Tests for seed_test_account()."""

    def test_creates_verified_account(self):
        """Seeding creates an account with a verified EmailAddress + PlayerData."""
        result = seed_test_account()

        self.assertTrue(result.created)
        self.assertEqual(result.username, "e2e_test_account")

        account = User.objects.get(username="e2e_test_account")
        self.assertEqual(account.email, "e2e_test@example.com")
        self.assertTrue(account.check_password("TestPass123!"))

        email_address = EmailAddress.objects.get(user=account)
        self.assertTrue(email_address.verified)
        self.assertTrue(email_address.primary)

        player_data = PlayerData.objects.get(account=account)
        self.assertIsNotNone(player_data)

    def test_idempotent(self):
        """Re-running on an existing account is a no-op."""
        first = seed_test_account()
        self.assertTrue(first.created)

        second = seed_test_account()
        self.assertFalse(second.created)

        # Only one account, one EmailAddress, one PlayerData
        self.assertEqual(User.objects.filter(username="e2e_test_account").count(), 1)
        self.assertEqual(EmailAddress.objects.filter(email="e2e_test@example.com").count(), 1)
        account = User.objects.get(username="e2e_test_account")
        self.assertEqual(PlayerData.objects.filter(account=account).count(), 1)

    def test_custom_credentials(self):
        """Custom username/email/password are respected."""
        result = seed_test_account(
            username="custom_tester",
            email="custom@test.com",
            password="CustomPass456!",
        )

        self.assertTrue(result.created)
        account = User.objects.get(username="custom_tester")
        self.assertEqual(account.email, "custom@test.com")
        self.assertTrue(account.check_password("CustomPass456!"))

    def test_preserves_existing_account(self):
        """Seeding does not overwrite an existing account's password."""
        User.objects.create_user(
            username="e2e_test_account",
            email="original@test.com",
            password="OriginalPass789!",
        )

        result = seed_test_account()
        self.assertFalse(result.created)

        account = User.objects.get(username="e2e_test_account")
        # Original password should still work
        self.assertTrue(account.check_password("OriginalPass789!"))
        # Email should not have changed
        self.assertEqual(account.email, "original@test.com")


class SeedTestAccountCommandTests(TestCase):
    """Tests for the management command."""

    def test_command_creates_account(self):
        out = StringIO()
        call_command("seed_test_account", stdout=out)
        self.assertIn("Created test account", out.getvalue())
        self.assertTrue(User.objects.filter(username="e2e_test_account").exists())

    def test_command_idempotent(self):
        call_command("seed_test_account")
        out = StringIO()
        call_command("seed_test_account", stdout=out)
        self.assertIn("already exists", out.getvalue())

    def test_command_custom_args(self):
        out = StringIO()
        call_command(
            "seed_test_account",
            "--username=cmd_tester",
            "--email=cmd@test.com",
            "--password=CmdPass123!",
            stdout=out,
        )
        self.assertTrue(User.objects.filter(username="cmd_tester").exists())
        account = User.objects.get(username="cmd_tester")
        self.assertTrue(account.check_password("CmdPass123!"))
