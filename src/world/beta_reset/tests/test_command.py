"""Command-layer argument-gating tests for ``arx manage beta_reset`` (#3055 PR 2).

Mirrors the ``call_command`` pattern in
``world/locations/tests/test_cleanup.py::CleanupDecayedModifiersCommandTests``.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.beta_reset.models import ReleaseLatch
from world.beta_reset.services import CONFIRMATION_PHRASE
from world.npc_services.factories import NPCStandingFactory
from world.npc_services.models import NPCStanding


class BetaResetCommandTests(TestCase):
    def test_bare_invocation_is_a_dry_run_and_touches_nothing(self) -> None:
        standing = NPCStandingFactory()

        out = StringIO()
        call_command("beta_reset", stdout=out)
        output = out.getvalue()

        self.assertIn("Would delete", output)
        self.assertIn("Dry run only", output)
        self.assertTrue(NPCStanding.objects.filter(pk=standing.pk).exists())

    def test_execute_without_confirm_raises_command_error_and_touches_nothing(self) -> None:
        standing = NPCStandingFactory()

        with self.assertRaises(CommandError):
            call_command(
                "beta_reset",
                "--execute",
                backup_verified_at=timezone.now().isoformat(),
            )

        self.assertTrue(NPCStanding.objects.filter(pk=standing.pk).exists())

    def test_execute_with_everything_correct_performs_the_wipe(self) -> None:
        standing = NPCStandingFactory()

        out = StringIO()
        call_command(
            "beta_reset",
            "--execute",
            confirm=CONFIRMATION_PHRASE,
            backup_verified_at=timezone.now().isoformat(),
            stdout=out,
        )

        self.assertIn("Deleted", out.getvalue())
        self.assertFalse(NPCStanding.objects.filter(pk=standing.pk).exists())

    def test_execute_blocked_by_release_latch_raises_command_error(self) -> None:
        account = AccountFactory()
        ReleaseLatch.objects.create(released_by=account)
        standing = NPCStandingFactory()

        with self.assertRaises(CommandError):
            call_command(
                "beta_reset",
                "--execute",
                confirm=CONFIRMATION_PHRASE,
                backup_verified_at=timezone.now().isoformat(),
            )

        self.assertTrue(NPCStanding.objects.filter(pk=standing.pk).exists())

    def test_malformed_backup_timestamp_raises_command_error(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "beta_reset",
                "--execute",
                confirm=CONFIRMATION_PHRASE,
                backup_verified_at="not-a-timestamp",
            )


class MarkBetaReleaseCommandTests(TestCase):
    def test_writes_the_latch_row(self) -> None:
        account = AccountFactory(username="cutover_staffer")

        out = StringIO()
        call_command("mark_beta_release", released_by="cutover_staffer", stdout=out)

        self.assertEqual(ReleaseLatch.objects.count(), 1)
        latch = ReleaseLatch.objects.get()
        self.assertEqual(latch.released_by_id, account.pk)
        self.assertIn("ReleaseLatch written", out.getvalue())

    def test_unknown_username_raises_command_error(self) -> None:
        with self.assertRaises(CommandError):
            call_command("mark_beta_release", released_by="nonexistent_user")

    def test_second_invocation_raises_command_error(self) -> None:
        account = AccountFactory(username="cutover_staffer")
        call_command("mark_beta_release", released_by="cutover_staffer")

        with self.assertRaises(CommandError):
            call_command("mark_beta_release", released_by=account.username)

        self.assertEqual(ReleaseLatch.objects.count(), 1)
