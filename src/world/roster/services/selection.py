"""Durable server-side character selection (#3412) and per-request identity (#3479).

Selection is NOT presence: ``set_selected_entry`` performs zero lifecycle,
session, or puppeting side effects. It is a plain fact the web client persists
so "who am I browsing as" survives a page reload before any presence step
(login, puppet) occurs. The sole mutator of ``PlayerData.selected_entry``.

Telnet independence (#3479 decision 10): this module is web-only substrate.
Telnet binds identity through Evennia session puppeting and never reads
``PlayerData.selected_entry`` or anything here (zero references under
``src/commands`` and ``src/server``); changing selection can never move a
telnet session, and no telnet change is needed when web identity semantics
change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.roster.models import RosterEntry

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from evennia.objects.models import ObjectDB
    from rest_framework.request import Request

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


def character_for_request(request: Request, *, entry_id: int | None) -> ObjectDB | None:
    """The character this request acts as (#3479 per-tab browsing identity).

    ``entry_id`` is the tab's explicit identity: it must name one of
    ``request.user``'s OWN current roster entries (the same population
    ``set_selected_entry`` accepts) and wins over the account column.
    ``None`` falls back to the durable selection (``selected_character``),
    which is how a fresh tab behaves before it has an identity of its own.

    Raises DRF ``PermissionDenied`` for any ``entry_id`` that does not
    resolve to an own entry. The owned list is the player's cached active
    tenures (``get_available_roster_entries``), so the lookup adds no query
    of its own and a foreign id and an unknown id are indistinguishable: the
    fixed message never leaks whether the entry exists at all.
    """
    from rest_framework.exceptions import PermissionDenied  # noqa: PLC0415

    from evennia_extensions.models import PlayerData  # noqa: PLC0415

    if entry_id is None:
        return selected_character(request.user)
    if not request.user.is_authenticated:
        raise PermissionDenied(SelectionError.user_message)
    player_data = PlayerData.objects.filter(account=request.user).first()
    if player_data is None:
        raise PermissionDenied(SelectionError.user_message)
    entry = next(
        (owned for owned in player_data.get_available_roster_entries() if owned.pk == entry_id),
        None,
    )
    if entry is None:
        raise PermissionDenied(SelectionError.user_message)
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
