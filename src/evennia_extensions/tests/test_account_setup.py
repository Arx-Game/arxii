"""Accounts that skipped Evennia's first-save setup heal themselves (#3812).

Django's ``create_superuser`` and pre-adapter web signup instantiate the bare
``AccountDB`` model. Evennia's ``post_save`` receiver for ``at_first_save()`` is
registered per typeclass proxy, so on those rows ``basetype_setup()`` never
runs: ``db_typeclass_path`` names the base model and ``db_cmdset_storage`` is
empty. The documented hand repair (``.update(db_typeclass_path=...)``) fixed the
first symptom and left the second, which is a row that can log in and run no
command at all — not even ``help``. These tests pin the heal that closes both.
"""

from __future__ import annotations

from django.conf import settings
from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.account_setup import (
    bare_account_rows,
    heal_account_setup,
    heal_bare_accounts,
    needs_account_setup,
)
from evennia_extensions.factories import AccountFactory

BARE_PATH = "evennia.accounts.models.AccountDB"


def _bare_row(username: str) -> AccountDB:
    """A row made the way ``createsuperuser`` makes one: the base model, saved."""
    row = AccountDB(username=username, email=f"{username}@example.com")
    row.set_password("x")
    row.save()
    return row


def _repointed_row(username: str) -> AccountDB:
    """The ops probe's documented repair: typeclass fixed by ``.update()``, nothing else."""
    _bare_row(username)
    AccountDB.objects.filter(username=username).update(
        db_typeclass_path=settings.BASE_ACCOUNT_TYPECLASS
    )
    AccountDB.flush_instance_cache()
    return AccountDB.objects.get(username=username)


def _command_keys(account: AccountDB) -> set[str]:
    account.cmdset.update()
    return {command.key for cmdset in account.cmdset.all() for command in cmdset.commands}


class NeedsAccountSetupTests(TestCase):
    def test_bare_row_needs_setup(self) -> None:
        row = _bare_row("bare")
        self.assertEqual(row.db_typeclass_path, BARE_PATH)
        self.assertFalse(row.db_cmdset_storage)
        self.assertTrue(needs_account_setup(row))

    def test_repointed_row_still_needs_setup(self) -> None:
        """The hand repair passes the old probe and leaves the account unusable."""
        row = _repointed_row("repointed")
        self.assertEqual(row.db_typeclass_path, settings.BASE_ACCOUNT_TYPECLASS)
        self.assertFalse(row.db_cmdset_storage)
        self.assertTrue(needs_account_setup(row))

    def test_healthy_account_does_not(self) -> None:
        account = AccountFactory()
        self.assertTrue(account.db_cmdset_storage)
        self.assertFalse(needs_account_setup(account))


class HealAccountSetupTests(TestCase):
    def test_heals_a_bare_row_into_a_working_account(self) -> None:
        row = _bare_row("bare")

        self.assertTrue(heal_account_setup(row))

        AccountDB.flush_instance_cache()
        healed = AccountDB.objects.get(username="bare")
        self.assertEqual(healed.db_typeclass_path, settings.BASE_ACCOUNT_TYPECLASS)
        self.assertEqual(healed.db_cmdset_storage, settings.CMDSET_ACCOUNT)
        self.assertIn("@ic", _command_keys(healed))
        self.assertIn(
            settings.PERMISSION_ACCOUNT_DEFAULT.lower(),
            {perm.lower() for perm in healed.permissions.all()},
        )

    def test_heals_the_repointed_shape_the_old_repair_left_behind(self) -> None:
        row = _repointed_row("repointed")
        self.assertEqual(_command_keys(row), set())

        self.assertTrue(heal_account_setup(row))

        self.assertIn("@ic", _command_keys(row))
        row.refresh_from_db()
        self.assertEqual(row.db_cmdset_storage, settings.CMDSET_ACCOUNT)

    def test_is_a_no_op_on_a_healthy_account(self) -> None:
        account = AccountFactory()
        before = account.db_cmdset_storage

        self.assertFalse(heal_account_setup(account))

        account.refresh_from_db()
        self.assertEqual(account.db_cmdset_storage, before)

    def test_healing_twice_does_not_stack_cmdsets(self) -> None:
        row = _bare_row("twice")
        heal_account_setup(row)
        heal_account_setup(row)
        row.refresh_from_db()
        self.assertEqual(row.db_cmdset_storage, settings.CMDSET_ACCOUNT)


class HealBareAccountsSweepTests(TestCase):
    def test_sweep_heals_every_shape_and_names_them(self) -> None:
        _bare_row("bare")
        _repointed_row("repointed")
        healthy = AccountFactory(username="healthy")
        healthy_storage = healthy.db_cmdset_storage

        healed = heal_bare_accounts()

        self.assertEqual(sorted(healed), ["bare", "repointed"])
        AccountDB.flush_instance_cache()
        for username in ("bare", "repointed"):
            row = AccountDB.objects.get(username=username)
            self.assertEqual(row.db_typeclass_path, settings.BASE_ACCOUNT_TYPECLASS)
            self.assertEqual(row.db_cmdset_storage, settings.CMDSET_ACCOUNT)
        self.assertEqual(
            AccountDB.objects.get(username="healthy").db_cmdset_storage, healthy_storage
        )
        self.assertEqual(list(bare_account_rows()), [])

    def test_sweep_is_empty_when_nothing_needs_healing(self) -> None:
        AccountFactory()
        self.assertEqual(heal_bare_accounts(), [])


class ServerStartHealsAccountsTests(TestCase):
    def test_at_server_start_runs_the_sweep(self) -> None:
        """A deploy fixes every affected account at once, with no shell access."""
        from unittest.mock import patch

        from server.conf import at_server_startstop

        with (
            patch("evennia_extensions.account_setup.heal_bare_accounts") as heal,
            patch("world.game_clock.tasks.register_all_tasks"),
            patch("world.game_clock.scripts.ensure_game_tick_script"),
        ):
            at_server_startstop.at_server_start()

        heal.assert_called_once_with()
