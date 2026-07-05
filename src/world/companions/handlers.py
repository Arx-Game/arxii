"""Handlers for Character access to Companion rows (#672)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.companions.models import Companion

if TYPE_CHECKING:
    from typeclasses.characters import Character


class CharacterCompanionHandler:
    """Handler for a character's bonded Companion rows.

    Mirrors the CharacterThreadHandler/CharacterConditionHandler cached-property
    handler pattern (world/magic/handlers.py, world/conditions/handlers.py).
    """

    def __init__(self, character: Character) -> None:
        self.character = character

    def active(self) -> list[Companion]:
        """This character's currently-bonded (unreleased) companions.

        Returns [] gracefully when the character has no sheet_data (mirrors
        the existing getattr(self, "sheet_data", None) guard pattern used
        throughout typeclasses/characters.py) — e.g. a CompanionObject or a
        GM/Staff character has no companions of its own.
        """
        sheet = getattr(self.character, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            return []
        return list(
            Companion.objects.filter(owner=sheet, released_at__isnull=True).select_related(
                "objectdb"
            )
        )
