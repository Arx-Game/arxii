"""Shared GM telnet target/account resolution helpers.

These utilities are intentionally thin and command-agnostic; they only resolve
objects and raise ``CommandError`` when the caller's input cannot be matched.
Game lifecycle behavior belongs in the actions/service layer, not here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from evennia.accounts.models import AccountDB

from commands.exceptions import CommandError
from world.character_sheets.models import CharacterSheet
from world.stories.models import Episode, Story

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet

_T = TypeVar("_T", bound="Model")

_NO_CONTROLLING_ACCOUNT = "No controlling account."


def resolve_actor_or_error(caller: object) -> AccountDB:
    """Return the ``AccountDB`` controlling *caller*, if any.

    Args:
        caller: The object executing the telnet command. Expected to expose
            ``active_account`` (e.g. a ``Character`` or ``Account``).

    Raises:
        CommandError: If *caller* has no controlling account.
    """
    try:
        account = caller.active_account
    except AttributeError:
        account = None
    if account is None:
        raise CommandError(_NO_CONTROLLING_ACCOUNT)
    return account


def resolve_account_or_none(caller: object) -> AccountDB | None:
    """Return the ``AccountDB`` controlling *caller*, or ``None``.

    Thin wrapper around ``resolve_actor_or_error`` for code paths that treat a
    missing account as a permission failure rather than a command error.
    """
    try:
        return resolve_actor_or_error(caller)
    except CommandError:
        return None


def resolve_model_by_pk_or_name(
    model: type[_T],
    value: str,
    *,
    qs: QuerySet[_T] | None = None,
    not_found_msg: str,
) -> _T:
    """Resolve a model instance by primary key or case-insensitive name.

    Numeric input is tried as a primary key first; otherwise an
    ``iexact`` lookup on the ``name`` field is used.

    Args:
        model: The Django model class to look up.
        value: The pk or name supplied by the caller.
        qs: Optional queryset to restrict the search. Defaults to
            ``model.objects.all()``.
        not_found_msg: Message raised in the ``CommandError`` when nothing
            matches.

    Raises:
        CommandError: When no matching instance is found.
    """
    queryset = qs if qs is not None else model.objects.all()

    try:
        if value.isdigit():
            instance = queryset.get(pk=value)
        else:
            instance = queryset.get(name__iexact=value)
    except (ObjectDoesNotExist, MultipleObjectsReturned) as exc:
        raise CommandError(not_found_msg) from exc

    return instance


def resolve_model_by_pk_or_title(
    model: type[_T],
    value: str,
    *,
    qs: QuerySet[_T] | None = None,
    not_found_msg: str,
    ambiguous_msg: str,
) -> _T:
    """Resolve a model instance by primary key or case-insensitive title.

    Numeric input is tried as a primary key first; otherwise an
    ``iexact`` lookup on the ``title`` field is used.

    Args:
        model: The Django model class to look up.
        value: The pk or title supplied by the caller.
        qs: Optional queryset to restrict the search. Defaults to
            ``model.objects.all()``.
        not_found_msg: Message raised in the ``CommandError`` when nothing
            matches.
        ambiguous_msg: Message raised in the ``CommandError`` when more than
            one instance matches the title.

    Raises:
        CommandError: When no matching instance is found or the title is not
            unique.
    """
    queryset = qs if qs is not None else model.objects.all()

    try:
        if value.isdigit():
            instance = queryset.get(pk=value)
        else:
            instance = queryset.get(title__iexact=value)
    except ObjectDoesNotExist as exc:
        raise CommandError(not_found_msg) from exc
    except MultipleObjectsReturned as exc:
        raise CommandError(ambiguous_msg) from exc

    return instance


def resolve_story_or_error(value: str) -> Story:
    """Resolve a ``Story`` by pk or title, raising ``CommandError`` on failure."""
    return resolve_model_by_pk_or_title(
        Story,
        value,
        not_found_msg="No story with that ID exists.",
        ambiguous_msg="More than one story matches that title.",
    )


def resolve_episode_or_error(value: str) -> Episode:
    """Resolve an ``Episode`` by pk or title, raising ``CommandError`` on failure."""
    return resolve_model_by_pk_or_title(
        Episode,
        value,
        not_found_msg="No episode with that ID exists.",
        ambiguous_msg="More than one episode matches that title.",
    )


def resolve_numeric_beat_id_or_error(value: str) -> str:
    """Return *value* if it is numeric, otherwise raise ``CommandError``.

    ``Beat`` has no title/name field, so it can only be resolved by pk.
    The backing action validates the actual pk existence.
    """
    if not value.isdigit():
        msg = "A beat must be specified by its numeric ID."
        raise CommandError(msg)
    return value


def resolve_character_sheet_in_room(
    caller: object,
    name_or_id: str,
    *,
    room: object,
) -> CharacterSheet:
    """Resolve a ``CharacterSheet`` belonging to a character in *room*.

    Args:
        caller: The command caller (unused except for consistent GM-helper
            signatures).
        name_or_id: The character's database ID or display name.
        room: The room whose occupants should be searched.

    Raises:
        CommandError: When no matching PC is present in the room.
    """
    del caller  # Reserved for a consistent GM-helper signature.

    # ``location`` is a wrapper around ``db_location`` on ObjectDB, so we
    # query the underlying column directly.
    base_qs = CharacterSheet.objects.filter(character__db_location=room)

    not_found_msg = f"No character named {name_or_id!r} here."

    try:
        if name_or_id.isdigit():
            sheet = base_qs.get(pk=name_or_id)
        else:
            sheet = base_qs.get(character__db_key__iexact=name_or_id)
    except (ObjectDoesNotExist, MultipleObjectsReturned) as exc:
        raise CommandError(not_found_msg) from exc

    return sheet
