"""Shared class-level advancement helpers (#1352).

Used by cross_threshold (Audere Majora) and the Ritual of the Durance to perform
the minimal level-write + cache invalidation on a character's primary class level.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.classes.models import CharacterClassLevel


def primary_class_level(character: ObjectDB) -> CharacterClassLevel | None:  # noqa: OBJECTDB_PARAM
    """Return the primary CharacterClassLevel, or the highest-level row, else None.

    Priority:
    1. The row marked is_primary=True.
    2. The row with the highest ``level`` value (when no primary is set).
    3. None when the character has no CharacterClassLevel rows at all.
    """
    from world.classes.models import CharacterClassLevel as _CharacterClassLevel

    primary = _CharacterClassLevel.objects.filter(character=character, is_primary=True).first()
    if primary is not None:
        return primary
    return _CharacterClassLevel.objects.filter(character=character).order_by("-level").first()


def apply_class_level_advance(sheet: CharacterSheet, *, level_after: int) -> None:
    """Write ``level_after`` to the primary CharacterClassLevel and invalidate the sheet cache.

    Pure level-write + cache invalidation — no receipt creation, no scene side-effects.
    Those belong to the caller (cross_threshold or the Durance action).

    No-op when the character has no CharacterClassLevel rows.
    """
    cl = primary_class_level(sheet.character)
    if cl is not None:
        cl.level = level_after
        cl.save(update_fields=["level"])
    sheet.invalidate_class_level_cache()
