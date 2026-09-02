"""Repoint accounts pinned to the bare ``AccountDB`` class at the Account typeclass.

Accounts created by allauth signup (``get_user_model()()``, before
``ArxAccountAdapter.new_user`` was overridden) or by Django's
``create_superuser`` never passed through Evennia's typeclass swap, so their
``db_typeclass_path`` names the bare model and they never load as
``typeclasses.accounts.Account``. Every view that reads typeclass state off
``request.user`` 500'd for them (Sentry ARX2-8, 2026-09-02). Account rows are
play state, not authored content; this is a repair, not a restructure.
"""

from django.conf import settings
from django.db import migrations

BARE_PATHS = ("", "evennia.accounts.models.AccountDB")


def repoint_bare_accounts(apps, schema_editor):
    del schema_editor
    AccountDB = apps.get_model("accounts", "AccountDB")
    AccountDB.objects.filter(db_typeclass_path__in=BARE_PATHS).update(
        db_typeclass_path=settings.BASE_ACCOUNT_TYPECLASS
    )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0212_alter_stakeresolution_machine_match_lifecycle_state"),
        ("accounts", "0012_defaultaccount_alter_accountdb_id_account_bot_and_more"),
    ]

    operations = [
        migrations.RunPython(repoint_bare_accounts, migrations.RunPython.noop),
    ]
