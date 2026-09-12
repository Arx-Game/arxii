"""``createsuperuser`` that leaves behind an account which can act (#3812).

Wins resolution over Django's command because ``core_management`` is first in
INSTALLED_APPS (see the ORDER IS LOAD-BEARING comment in ``server/conf/settings.py``);
``core_management.tests.test_createsuperuser`` pins it.

Django's ``create_superuser`` instantiates the bare ``AccountDB`` model, so Evennia's
per-typeclass ``post_save`` receiver never runs ``at_first_save()``: no typeclass path,
no cmdset storage, no default permission. The production deploy creates the
superuser exactly this way (``python -m django createsuperuser --noinput``), which is
how the staff account shipped able to log in and unable to run ``@ic``. Django's
own input handling (prompts, ``DJANGO_SUPERUSER_*`` for ``--noinput``, validation)
is kept as-is; after it returns, the sweep heals whichever row it just made — the
same ``swap_typeclass(run_start_hooks="all")`` the server runs on start.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.management.commands.createsuperuser import (
    Command as CreatesuperuserCommand,
)


class Command(CreatesuperuserCommand):
    def handle(self, *args: Any, **options: Any) -> Any:
        from evennia_extensions.account_setup import heal_bare_accounts  # noqa: PLC0415

        result = super().handle(*args, **options)
        heal_bare_accounts()
        return result
