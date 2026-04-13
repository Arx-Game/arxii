"""
Roster selector functions.

Shared utilities for resolving accounts from characters via roster tenure,
plus planned selector functions for character application filtering.
"""

from __future__ import annotations

from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

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
