"""Contributor identity resolution for the Authoring Workbench setup gate (#3019).

The dashboard (`web.admin.authoring.views.authoring_dashboard`) will not show
the stats/queue panels to an account that has no linked `ContentContributor` -
every credited-content view downstream of the backlog assumes a contributor
identity exists, so the gate gets one in place before anything else runs.
`current_contributor` reads that link; `link_contributor` writes it, in one
atomic create-or-pick step driven by the setup panel's plain POST.
"""

from __future__ import annotations

from django.db import transaction
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.contributors.models import ContentContributor

_DASH_CHARACTERS = "–—"  # en dash, em dash

_DASH_NAME_MESSAGE = (
    "Contributor names use a hyphen, not a dash. Retype the name with a hyphen instead."
)


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
    account, existing_pk already linked elsewhere. Creates PlayerData for the
    account if absent. Picking an UNLINKED existing contributor by exact name
    match through the create path links it rather than erroring on unique.
    """
    with transaction.atomic():
        player_data, _created = PlayerData.objects.get_or_create(account=user)

        if existing_pk is not None:
            try:
                contributor = ContentContributor.objects.get(pk=existing_pk)
            except ContentContributor.DoesNotExist as exc:
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
