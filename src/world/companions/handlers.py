"""Handlers for Character access to Companion rows (#672)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.functional import cached_property

from world.companions.models import Companion

if TYPE_CHECKING:
    from typeclasses.characters import Character


class CharacterCompanionHandler:
    """Handler for a character's bonded Companion rows.

    Mirrors the CharacterThreadHandler/CharacterConditionHandler cached-property
    handler pattern (world/magic/handlers.py, world/conditions/handlers.py): the
    active list is loaded once per Character instance and every later read, and
    every name or pk lookup, is query-free. ``bind_companion`` and
    ``release_companion`` call ``invalidate()`` after they write, so a command
    that reads the list after a bind sees the new row (#3657 tranche 17: the
    ``companion order`` parser had run one query per typed token instead).
    """

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _active(self) -> list[Companion]:
        sheet = self.character.character_sheet
        if sheet is None:
            return []
        return list(
            Companion.objects.filter(owner=sheet, released_at__isnull=True).select_related(
                "objectdb"
            )
        )

    def active(self) -> list[Companion]:
        """This character's currently-bonded (unreleased) companions.

        Returns [] gracefully when the character has no sheet_data (mirrors
        the existing self.character_sheet guard pattern used
        throughout typeclasses/characters.py) — e.g. a CompanionObject or a
        GM/Staff character has no companions of its own. One query on first
        access; cached until ``invalidate()``.
        """
        return self._active

    def find(self, value: str) -> Companion | None:
        """The active companion *value* names, by pk (all digits) or case-insensitive name.

        Walks the cached list, so a lookup costs no query. Where two companions share
        a name the newest bond wins, the order ``Companion.Meta.ordering`` gives.
        """
        if value.isdigit():
            pk = int(value)
            return next((c for c in self._active if c.pk == pk), None)
        wanted = value.casefold()
        return next((c for c in self._active if c.name.casefold() == wanted), None)

    def invalidate(self) -> None:
        """Drop the cached list so the next read re-queries.

        Called by the companion services that create or release a row.
        """
        self.__dict__.pop("_active", None)
