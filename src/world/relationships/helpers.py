"""Helper functions for the relationships system."""

from evennia.objects.models import ObjectDB


def get_relationship_tier(
    character_a: ObjectDB,  # noqa: ARG001 - stub, will use when tiers are implemented
    character_b: ObjectDB,  # noqa: ARG001 - stub, will use when tiers are implemented
) -> int:
    """Get the relationship tier between two characters.

    TODO: Implement actual tier calculation from RelationshipTrackProgress
    point values once tier breakpoints are defined. Currently returns 0
    (no relationship bonus). The training system uses this as:
    mentor_bonus *= (relationship_tier + 1)

    Args:
        character_a: First character.
        character_b: Second character.

    Returns:
        Relationship tier as an integer (0 = no/new relationship).
    """
    return 0
