"""``createsuperuser`` must produce an account that can act (#3812).

The production deploy creates the superuser with ``python -m django
createsuperuser --noinput`` (``infra/ansible/roles/app_deploy/tasks/main.yml``).
Django's ``create_superuser`` instantiates the bare ``AccountDB`` model, so
Evennia's per-typeclass ``post_save`` receiver never runs ``at_first_save()``:
the row logs in, prints its character list, and can run no command at all.
``core_management`` overrides the command to heal the row it just made. As
with ``makemigrations`` (#2885), the override only exists if it *resolves*, so
the first test asserts resolution, never the class in isolation.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command, get_commands
from django.test import SimpleTestCase, TestCase
from evennia.accounts.models import AccountDB


class CreatesuperuserResolutionTests(SimpleTestCase):
    def test_createsuperuser_resolves_to_core_management(self) -> None:
        assert get_commands()["createsuperuser"] == "core_management"


class CreatesuperuserHealsTheRowTests(TestCase):
    def test_noinput_superuser_is_a_typeclassed_account_with_a_cmdset(self) -> None:
        with patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": "hunter2hunter2"}):
            call_command(
                "createsuperuser",
                interactive=False,
                username="deploy_su",
                email="su@example.com",
                stdout=StringIO(),
            )

        AccountDB.flush_instance_cache()
        row = AccountDB.objects.get(username="deploy_su")
        self.assertTrue(row.is_superuser)
        self.assertEqual(row.db_typeclass_path, settings.BASE_ACCOUNT_TYPECLASS)
        self.assertEqual(row.db_cmdset_storage, settings.CMDSET_ACCOUNT)
        row.cmdset.update()
        keys = {command.key for cmdset in row.cmdset.all() for command in cmdset.commands}
        self.assertIn("@ic", keys)
