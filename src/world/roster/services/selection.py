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
    from evennia_extensions.models import PlayerData


class SelectionError(ValueError):
    """A ``set_selected_entry`` call targeting an entry that isn't the
    account's own current roster entry.

    Carries a fixed ``user_message`` (per ``feedback_codeql_exceptions``) so
    the select endpoint can surface a safe string without leaking whether the
    entry id exists at all.
    """

    user_message = "That isn't one of your characters."


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
