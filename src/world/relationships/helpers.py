"""Helper functions for the relationships system."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet


def get_relationship_tier(
    character_a: CharacterSheet | ObjectDB, character_b: CharacterSheet | ObjectDB
) -> int:
    """The lower claimed tier of a mutual Mentor/Student tie, else 0 (#3957).

    Training's mentor multiplier reads this as ``(tier + 1)``: it rewards a real
    mentorship, which is two sides that both said so and both invested.

    Takes a sheet or a character on either side and narrows to the sheet itself — the
    annotation says both because both arrive (#3957 final review); a bare ``ObjectDB``
    annotation over an ``isinstance`` narrow claims a shape the callers do not honour.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.relationships.constants import TypeFamily  # noqa: PLC0415
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415
    from world.relationships.services import is_mutual  # noqa: PLC0415

    def _sheet(character):
        if isinstance(character, CharacterSheet):
            return character
        return character.character_sheet

    sheet_a, sheet_b = _sheet(character_a), _sheet(character_b)
    if sheet_a is None or sheet_b is None:
        return 0
    side = CharacterRelationship.objects.filter(source=sheet_a, target=sheet_b).first()
    if side is None:
        return 0
    # Bound once: ``reverse`` is a plain property (#3957 review -- an idmapper-shared
    # instance must not carry an uninvalidated cache), so reading it twice would cost
    # two identical queries per call.
    other = side.reverse
    if other is None:
        return 0
    teaching_labels = side.open_labels().filter(type__family=TypeFamily.TEACHING)
    # any() short-circuits at the first mutual match -- is_mutual's own two queries
    # only run per label up to that point, not for the whole teaching_labels set.
    if not any(is_mutual(side, label.type) for label in teaching_labels):
        return 0
    return min(side.tier, other.tier)
