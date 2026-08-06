"""Contributor identity resolution for the Authoring Workbench setup gate (#3019).

The dashboard (`web.admin.authoring.views.authoring_dashboard`) will not show
the stats/queue panels to an account that has no linked `ContentContributor` -
every credited-content view downstream of the backlog assumes a contributor
identity exists, so the gate gets one in place before anything else runs.
`current_contributor` reads that link; `link_contributor` writes it, in one
atomic create-or-pick step driven by the setup panel's plain POST.

`link_contributor` does an unlocked read-then-write against three unique
columns (`ContentContributor.name`, the `PlayerData.contributor` O2O,
`PlayerData.account`'s primary key), so two concurrent submits can both pass
the read and then race the write. That race surfaces as `IntegrityError`,
caught around (not inside) the atomic block so the failed transaction has
already rolled back before `current_contributor` re-checks it: if the racing
request linked this same account, that is an idempotent success (see
`authoring_setup`'s already-linked no-op); otherwise the caller gets a
coherent `ValueError` instead of a 500.
"""

from __future__ import annotations

from django.db import DataError, IntegrityError, transaction
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.contributors.models import ContentContributor

_DASH_CHARACTERS = "–—"  # en dash, em dash

_DASH_NAME_MESSAGE = (
    "Contributor names use a hyphen, not a dash. Retype the name with a hyphen instead."
)

_RACE_MESSAGE = "That name was claimed a moment ago. Pick it from the list or choose another."


def current_contributor(user: AccountDB) -> ContentContributor | None:
    """request.user -> PlayerData -> contributor; None at any missing link."""
    try:
        player_data = user.player_data
    except AttributeError:
        return None
    return player_data.contributor


def _refuse_if_linked_elsewhere(contributor: ContentContributor, player_data: PlayerData) -> None:
    try:
        linked = contributor.player_data
    except AttributeError:
        return
    if linked.pk != player_data.pk:
        msg = f'"{contributor.name}" is already linked to another account.'
        raise ValueError(msg)


def link_contributor(
    user: AccountDB, *, name: str = "", existing_pk: int | None = None
) -> ContentContributor:
    """Create-or-pick and link atomically; returns the contributor.

    Raises ValueError with a user-facing message on: blank name, em/en dash
    in name, name colliding with a contributor already linked to another
    account, existing_pk already linked elsewhere, existing_pk out of range.
    Creates PlayerData for the account if absent. Picking an UNLINKED existing
    contributor by exact name match through the create path links it rather
    than erroring on unique.

    A write that loses a concurrent-submit race raises IntegrityError inside
    the atomic block, which is caught here only after the block has rolled
    back: if the race already linked this account, that link is returned as
    an idempotent success; otherwise ValueError reports the coherent "someone
    else just took it" outcome instead of letting the 500 through.
    """
    try:
        with transaction.atomic():
            player_data, _created = PlayerData.objects.get_or_create(account=user)

            if existing_pk is not None:
                try:
                    contributor = ContentContributor.objects.get(pk=existing_pk)
                except (
                    ContentContributor.DoesNotExist,
                    ValueError,
                    OverflowError,
                    DataError,
                ) as exc:
                    msg = "That contributor no longer exists."
                    raise ValueError(msg) from exc
                _refuse_if_linked_elsewhere(contributor, player_data)
            else:
                stripped_name = name.strip()
                if not stripped_name:
                    msg = "Enter a name to write under."
                    raise ValueError(msg)
                if any(char in stripped_name for char in _DASH_CHARACTERS):
                    raise ValueError(_DASH_NAME_MESSAGE)

                contributor = ContentContributor.objects.filter(name=stripped_name).first()
                if contributor is not None:
                    _refuse_if_linked_elsewhere(contributor, player_data)
                else:
                    contributor = ContentContributor.objects.create(name=stripped_name)

            player_data.contributor = contributor
            player_data.save()
            return contributor
    except IntegrityError as exc:
        raced_contributor = current_contributor(user)
        if raced_contributor is not None:
            return raced_contributor
        raise ValueError(_RACE_MESSAGE) from exc
