"""Helper functions for the relationships system."""

from evennia.objects.models import ObjectDB


def get_relationship_tier(character_a: ObjectDB, character_b: ObjectDB) -> int:
    """The lower claimed tier of a mutual Mentor/Student tie, else 0 (#3957).

    Training's mentor multiplier reads this as ``(tier + 1)``: it rewards a real
    mentorship, which is two sides that both said so and both invested.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
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
    if side is None or side.reverse is None:
        return 0
    teaching_labels = side.open_labels().filter(type__family="teaching")
    if not any(is_mutual(side, label.type) for label in teaching_labels):
        return 0
    return min(side.tier, side.reverse.tier)
