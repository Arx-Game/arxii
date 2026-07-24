"""Helper functions for the relationships system."""

from evennia.objects.models import ObjectDB

from world.relationships.models import CharacterRelationship


def get_relationship_tier(character_a: ObjectDB, character_b: ObjectDB) -> int:
    """Highest relationship tier character_a holds toward character_b (0 = none).

    Looks up the CharacterRelationship from character_a to character_b and returns
    the maximum tier_number crossed across all track progress entries, based on
    developed (permanent) points. Returns 0 if no relationship exists, if either
    character lacks a CharacterSheet, or if no tier threshold has been crossed.

    The training system uses this as: mentor_bonus *= (relationship_tier + 1).

    Args:
        character_a: The character holding the relationship (source).
        character_b: The character the relationship is about (target).

    Returns:
        Relationship tier as an integer (0 = no/new relationship).
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    if isinstance(character_a, CharacterSheet):
        sheet_a = character_a
    else:
        sheet_a = character_a.character_sheet
    if isinstance(character_b, CharacterSheet):
        sheet_b = character_b
    else:
        sheet_b = character_b.character_sheet
    if sheet_a is None or sheet_b is None:
        return 0
    rel = CharacterRelationship.objects.filter(source=sheet_a, target=sheet_b).first()
    if rel is None:
        return 0
    best = 0
    for progress in rel.track_progress.all():
        tier = progress.current_tier
        if tier is not None:
            best = max(best, tier.tier_number)
    return best
