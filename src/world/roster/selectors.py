"""
Roster selector functions.

Shared utilities for resolving accounts from characters via roster tenure,
plus planned selector functions for character application filtering.
"""

from __future__ import annotations

from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterSheet
from world.roster.models import RosterTenure


def get_account_for_character(character: ObjectDB) -> AccountDB | None:
    """Get the account currently playing this character via roster tenure.

    Args:
        character: An ObjectDB instance (Evennia character).

    Returns the account or None if no active tenure.
    """
    tenure = (
        RosterTenure.objects.filter(
            roster_entry__character_sheet__character=character,
            end_date__isnull=True,
        )
        .select_related("player_data__account")
        .first()
    )
    if tenure is None:
        return None
    return tenure.player_data.account


def active_player_character_sheets() -> list[CharacterSheet]:
    """Return every CharacterSheet whose roster_entry has a current (unended) tenure.

    "Current tenure" means a RosterTenure with end_date__isnull=True, matching
    the RosterTenure.is_current property definition (tenures.py:117).

    Filters on tenure pk__isnull=False to avoid the LEFT JOIN / NULL ambiguity
    (a sheet with no tenures would otherwise pass the end_date__isnull=True check).

    Returns a de-duplicated list in a single query; no queries-in-loops.
    """
    return list(
        CharacterSheet.objects.filter(
            roster_entry__tenures__pk__isnull=False,
            roster_entry__tenures__end_date__isnull=True,
        )
        .select_related("roster_entry")
        .distinct()
    )


def puppeted_sheet_for(user: object) -> CharacterSheet | None:
    """The CharacterSheet of the character ``user`` is currently puppeting, or None.

    The canonical user→puppet→sheet resolver (silent-fail audit): ``Account.puppet``
    can be a truthy non-character object for sessionless accounts, and AnonymousUser
    has no puppet attribute at all — inline ``puppet.character_sheet`` dances 500'd
    the summons list and silently degraded drf-spectacular's queryset inference.
    """
    puppet = getattr(user, "puppet", None)  # noqa: GETATTR_LITERAL — AnonymousUser has none
    if not isinstance(puppet, ObjectDB):
        return None
    return puppet.character_sheet
