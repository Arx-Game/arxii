"""Migration 0211 repoints bare ``AccountDB`` rows at the Account typeclass.

Accounts created by allauth signup (before the adapter fix) or by Django's
``create_superuser`` carry ``db_typeclass_path`` of the bare model, so they
never load as ``typeclasses.accounts.Account`` (Sentry ARX2-8).
"""

import importlib

from django.apps import apps
from django.conf import settings
from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import AccountFactory

BACKFILL = importlib.import_module("world.migrations.0211_account_typeclass_backfill")


class AccountTypeclassBackfillTests(TestCase):
    def test_bare_rows_are_repointed_and_typeclassed_rows_untouched(self) -> None:
        bare = AccountDB.objects.create_superuser("bare_root", "root@example.com", "pw")
        typed = AccountFactory(username="typed_player")
        self.assertEqual(bare.db_typeclass_path, "evennia.accounts.models.AccountDB")
        self.assertEqual(typed.db_typeclass_path, settings.BASE_ACCOUNT_TYPECLASS)

        BACKFILL.repoint_bare_accounts(apps, None)

        self.assertEqual(
            AccountDB.objects.values_list("db_typeclass_path", flat=True).get(pk=bare.pk),
            settings.BASE_ACCOUNT_TYPECLASS,
        )
        self.assertEqual(
            AccountDB.objects.values_list("db_typeclass_path", flat=True).get(pk=typed.pk),
            settings.BASE_ACCOUNT_TYPECLASS,
        )
