"""Complete Evennia's first-save setup on account rows that never got it (#3812).

Evennia wires ``at_first_save()`` — which runs ``basetype_setup()`` (lockstring +
the persistent account cmdset), ``at_account_creation()`` and the default
``Player`` permission — to ``post_save``, registered **per typeclass proxy**. A
row saved as the bare ``AccountDB`` model never fires it. Two paths make such
rows: Django's ``create_superuser`` (the production deploy's
``python -m django createsuperuser --noinput``) and web signup before
``ArxAccountAdapter.new_user`` existed. The row logs in, prints its character
list, and can run no command at all — ``Command '@ic X' is not available``,
and ``help`` fails the same way.

Repointing ``db_typeclass_path`` by hand (what the ops probe used to prescribe)
fixes the typeclass and nothing else: a plain ``.update()`` runs no hook, so
``db_cmdset_storage`` stays empty and the account still has zero commands.
The heal here is Evennia's own answer to "replay first-save setup on an
existing row": ``swap_typeclass(..., run_start_hooks="all")``. It runs from
three places — the server-start sweep (every affected account is fixed by the
first deploy, no shell needed), ``Account.at_pre_login`` as a guard, and the
``createsuperuser`` override that heals the row it just made.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db.models import Q, QuerySet
from evennia.accounts.models import AccountDB

logger = logging.getLogger(__name__)

#: ``db_typeclass_path`` values that mean "never went through a typeclass".
BARE_TYPECLASS_PATHS: tuple[str, ...] = ("", "evennia.accounts.models.AccountDB")


def needs_account_setup(account: AccountDB) -> bool:
    """True when ``account`` skipped first-save setup on either axis.

    Either symptom alone is disqualifying: a bare typeclass path (the row loads
    without the ``Account`` typeclass) or an empty cmdset storage (the row has
    no commands). The second is the one a hand-repointed row still carries.
    """
    bare_path = (account.db_typeclass_path or "") in BARE_TYPECLASS_PATHS
    return bare_path or not account.db_cmdset_storage


def heal_account_setup(account: AccountDB) -> bool:
    """Run first-save setup on ``account`` if it never happened. Idempotent.

    ``swap_typeclass`` sets the typeclass path, rebinds the instance's class
    in place, and with ``run_start_hooks="all"`` calls ``at_first_save()`` —
    the exact sequence creation runs. ``basetype_setup`` adds the default
    cmdset with ``persistent=True``, which both writes ``db_cmdset_storage``
    and rebuilds the live cmdset, so a heal during ``at_pre_login`` takes
    effect for that very login. Returns whether anything was done.
    """
    if not needs_account_setup(account):
        return False
    account.swap_typeclass(settings.BASE_ACCOUNT_TYPECLASS, run_start_hooks="all")
    logger.info("Completed first-save setup on account %r (#3812).", account.username)
    return True


def bare_account_rows() -> QuerySet[AccountDB]:
    """Every account row that ``needs_account_setup``, as a queryset."""
    return AccountDB.objects.filter(
        Q(db_typeclass_path__in=BARE_TYPECLASS_PATHS)
        | Q(db_cmdset_storage__isnull=True)
        | Q(db_cmdset_storage="")
    ).order_by("id")


def heal_bare_accounts() -> list[str]:
    """Heal every row that needs it; return the usernames touched.

    Called from ``at_server_start`` so a deploy fixes every affected account
    at once, and after ``createsuperuser`` so the row it made never ships bare.
    """
    healed = [account.username for account in bare_account_rows() if heal_account_setup(account)]
    if healed:
        logger.info("Healed %d account(s) that skipped first-save setup: %s", len(healed), healed)
    return healed
