from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.request import Request

if TYPE_CHECKING:
    from world.roster.models import RosterEntry


def get_roster_entry_from_request(request: Request) -> RosterEntry | None:
    """Extract the current player's roster entry from the request.

    Resolves through: request.user -> puppeted character -> roster_entry.
    Returns None if any step fails (unauthenticated, no puppet, no roster entry).
    """
    user = request.user
    if not user.is_authenticated:
        return None
    puppets = user.get_puppeted_characters()
    if not puppets:
        return None
    character = puppets[0]
    try:
        return character.roster_entry
    except AttributeError:
        return None
