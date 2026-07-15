"""Dream engagement gate — prevents voluntary wake during dream danger (#2290).

A sleeping character is "dream-engaged" when there is an active SceneRound
(DECLARING or RESOLVING) whose room is the character's dream room.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def is_dream_engaged(character_sheet: CharacterSheet | None) -> bool:
    """True when an active scene round exists in the character's dream room.

    Args:
        character_sheet: The character's sheet.

    Returns:
        True if the character is dream-engaged (cannot voluntarily wake).
    """
    if character_sheet is None:
        return False
    character = character_sheet.character
    from world.dreams.services import get_dream_space  # noqa: PLC0415

    dream_room = get_dream_space(room=character.location)
    if dream_room is None:
        return False
    from world.scenes.models import SceneRound  # noqa: PLC0415

    return SceneRound.objects.filter(
        room=dream_room,
        status__in=["DECLARING", "RESOLVING"],
    ).exists()
