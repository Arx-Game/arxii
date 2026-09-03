"""Durable server-side character selection — state 2.5 substrate (#3412).

Selection is NOT presence: ``set_selected_entry`` performs zero lifecycle,
session, or puppeting side effects. It is a plain fact the web client persists
so "who am I browsing as" survives a page reload before any presence step
(login, puppet) occurs. The sole mutator of ``PlayerData.selected_entry``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.roster.models import RosterEntry

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import PlayerData


class SelectionError(ValueError):
    """A ``set_selected_entry`` call targeting an entry that isn't the
    account's own current roster entry.

    Carries a fixed ``user_message`` (per ``feedback_codeql_exceptions``) so
    the select endpoint can surface a safe string without leaking whether the
    entry id exists at all.
    """

    user_message = "That isn't one of your characters."


def selected_character(account: AbstractBaseUser | AnonymousUser) -> ObjectDB | None:
    """The character ``account`` has taken up offscreen (#3412), or ``None``.

    This is how a web endpoint learns "who am I acting as": the durable
    selection needs no live session and no typeclass. It replaces reading
    ``Account.puppet`` off ``request.user``, which under ``MULTISESSION_MODE
    = 2`` is the *list* of all puppets (empty, never ``None``, with no
    session) and does not exist at all on the base ``AccountDB`` (Sentry
    ARX2-7, 2026-09-02).
    """
    from evennia_extensions.models import PlayerData  # noqa: PLC0415

    if not account.is_authenticated:
        return None
    player_data = (
        PlayerData.objects.filter(account=account)
        .select_related("selected_entry__character_sheet__character")
        .first()
    )
    entry = player_data.selected_entry if player_data is not None else None
    if entry is None:
        return None
    return entry.character_sheet.character


def set_selected_entry(player_data: PlayerData, entry: RosterEntry | None) -> None:
    """Set (or clear) the account's durable character selection.

    ``entry`` must be one of the account's own current roster entries — the
    same population ``RosterEntryViewSet.mine`` exposes
    (``PlayerData.get_available_characters()``: an active, non-retired tenure
    on an active roster). Clearing (``entry=None``) is always allowed.

    Raises ``SelectionError`` for a foreign or otherwise ineligible entry.
    Never touches presence/session/puppeting state.
    """
    if entry is not None:
        available_characters = player_data.get_available_characters()
        is_own_entry = RosterEntry.objects.filter(
            pk=entry.pk,
            character_sheet__character__in=available_characters,
        ).exists()
        if not is_own_entry:
            raise SelectionError
    player_data.selected_entry = entry
    player_data.save(update_fields=["selected_entry"])
