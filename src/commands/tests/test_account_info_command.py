"""Tests for #2122's telnet onboarding + visibility polish additions to
``commands/account/account_info.py``:

- ``CmdRoster`` (``roster``/``roster status``) — own pending applications only.
- ``CmdAccount``'s new ``account email <address>`` subverb.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from allauth.account.models import EmailAddress
from django.test import TestCase

from commands.account.account_info import CmdAccount, CmdRoster
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterApplicationFactory
from world.roster.models.choices import ApplicationStatus


def _make_roster_cmd(account, args=""):
    cmd = CmdRoster()
    cmd.account = account
    cmd.caller = account
    cmd.args = args
    cmd.raw_string = f"roster {args}".strip()
    cmd.cmdname = "roster"
    return cmd


def _make_account_cmd(account, args=""):
    cmd = CmdAccount()
    cmd.account = account
    cmd.caller = account
    cmd.args = args
    cmd.raw_string = f"account {args}".strip()
    cmd.cmdname = "account"
    return cmd


class CmdRosterStatusTests(TestCase):
    """``roster status`` shows only the caller's own pending applications."""

    def setUp(self):
        self.account = AccountFactory()
        self.player_data = self.account.player_data  # ensure PlayerData exists
        self.account.msg = MagicMock()

    def _sent_text(self, args=""):
        cmd = _make_roster_cmd(self.account, args)
        cmd.func()
        return "\n".join(str(c.args[0]) for c in self.account.msg.call_args_list)

    def test_no_pending_applications(self):
        sent = self._sent_text()
        self.assertIn("no pending roster applications", sent.lower())

    def test_bare_and_status_are_equivalent(self):
        character = CharacterFactory(db_key="Applicant")
        RosterApplicationFactory(
            player_data=self.account.player_data,
            character=character,
            status=ApplicationStatus.PENDING,
        )
        bare = self._sent_text("")
        self.account.msg.reset_mock()
        status = self._sent_text("status")
        self.assertIn(character.key, bare)
        self.assertIn(character.key, status)

    def test_own_pending_application_shown(self):
        character = CharacterFactory(db_key="Hopeful")
        RosterApplicationFactory(
            player_data=self.account.player_data,
            character=character,
            status=ApplicationStatus.PENDING,
        )
        sent = self._sent_text("status")
        self.assertIn("Hopeful", sent)
        self.assertIn("Pending", sent)

    def test_approved_application_not_shown(self):
        character = CharacterFactory(db_key="AlreadyIn")
        RosterApplicationFactory(
            player_data=self.account.player_data,
            character=character,
            status=ApplicationStatus.APPROVED,
        )
        sent = self._sent_text("status")
        self.assertIn("no pending roster applications", sent.lower())

    def test_another_accounts_application_never_shown(self):
        """Leak negative (#2122 leak analysis) — scoped to the caller's own PlayerData."""
        other_player_data = PlayerDataFactory()
        other_character = CharacterFactory(db_key="NotYours")
        RosterApplicationFactory(
            player_data=other_player_data,
            character=other_character,
            status=ApplicationStatus.PENDING,
        )
        sent = self._sent_text("status")
        self.assertNotIn("NotYours", sent)
        self.assertIn("no pending roster applications", sent.lower())

    def test_unknown_subverb_reports_usage(self):
        sent = self._sent_text("browse")
        self.assertIn("Unknown roster command", sent)


class CmdAccountEmailTests(TestCase):
    """``account email <address>`` sets/updates the primary email + confirmation (#2122)."""

    def setUp(self):
        self.account = AccountFactory()
        self.player_data = self.account.player_data  # ensure PlayerData exists
        self.account.msg = MagicMock()

    def _run(self, args):
        cmd = _make_account_cmd(self.account, args)
        cmd.func()
        return "\n".join(str(c.args[0]) for c in self.account.msg.call_args_list)

    def test_invalid_address_rejected(self):
        sent = self._run("email not-an-email")
        self.assertIn("doesn't look like a valid email address", sent)
        self.assertFalse(EmailAddress.objects.filter(user=self.account).exists())

    def test_sets_unverified_primary_email_and_sends_confirmation(self):
        sent = self._run("email newplayer@example.com")

        email_address = EmailAddress.objects.get(user=self.account, email="newplayer@example.com")
        self.assertTrue(email_address.primary)
        self.assertFalse(email_address.verified)
        self.assertIn("verification link has been sent", sent)

        # can_apply_for_characters stays False until verification (#2122 journey).
        self.assertFalse(self.account.player_data.can_apply_for_characters())

    def test_verifying_flips_can_apply_for_characters(self):
        self._run("email newplayer@example.com")
        email_address = EmailAddress.objects.get(user=self.account, email="newplayer@example.com")

        email_address.verified = True
        email_address.save(update_fields=["verified"])

        self.assertTrue(self.account.player_data.can_apply_for_characters())

    def test_rerunning_on_already_verified_email_is_a_no_op_message(self):
        self._run("email newplayer@example.com")
        email_address = EmailAddress.objects.get(user=self.account, email="newplayer@example.com")
        email_address.verified = True
        email_address.save(update_fields=["verified"])
        self.account.msg.reset_mock()

        sent = self._run("email newplayer@example.com")
        self.assertIn("already set and verified", sent)

    def test_only_touches_own_account(self):
        """No target-account argument exists — the command can't touch another account's email."""
        other = AccountFactory()
        _ = other.player_data
        self._run("email newplayer@example.com")
        self.assertFalse(EmailAddress.objects.filter(user=other).exists())
