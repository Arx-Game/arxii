"""Service helpers for the classes app."""

from world.classes.models import PathStage

# (min_level, stage) descending — first whose min_level <= level wins.
_STAGE_THRESHOLDS: list[tuple[int, int]] = [
    (21, PathStage.TRANSCENDENT),
    (16, PathStage.GRAND),
    (11, PathStage.TRUE),
    (6, PathStage.PUISSANT),
    (3, PathStage.POTENTIAL),
    (1, PathStage.PROSPECT),
]


def stage_for_level(level: int) -> int:
    """Map a class level to its PathStage value (clamps <1 to PROSPECT)."""
    for min_level, stage in _STAGE_THRESHOLDS:
        if level >= min_level:
            return stage
    return PathStage.PROSPECT


def is_crossing_level(level: int) -> bool:
    """Return True if ``level`` is a PathStage crossing boundary.

    A crossing level is one where ``stage_for_level(level)`` differs from
    ``stage_for_level(level - 1)`` — i.e. levels 3, 6, 11, 16, 21. Used by
    the imbuing loop to decide whether to check for a
    ``ThreadCrossingThreshold`` gate before advancing (#1885).
    """
    if level < 1:
        return False
    return stage_for_level(level) != stage_for_level(level - 1)


def set_primary_class_level(  # noqa: OBJECTDB_PARAM
    character: object,
    character_class: object,
    level: int,
) -> object:
    """Set the character's primary class level and recompute level-derived health.

    Upserts a CharacterClassLevel row (keyed on character + character_class) with
    is_primary=True and the given level, then triggers a full max_health recompute
    so the character's vitals reflect the new level immediately.

    This is the documented hook for all level changes — callers should never mutate
    CharacterClassLevel rows directly.

    Args:
        character: The character whose class level is being set (ObjectDB instance).
        character_class: The CharacterClass to assign.
        level: The new level value (1–30).

    Returns:
        The upserted CharacterClassLevel instance.
    """
    from world.classes.models import CharacterClassLevel  # noqa: PLC0415
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415

    sheet = character.sheet_data
    CharacterClassLevel.objects.filter(character=sheet, is_primary=True).exclude(
        character_class=character_class
    ).update(is_primary=False)
    CharacterClassLevel.flush_instance_cache()
    ccl, _ = CharacterClassLevel.objects.update_or_create(
        character=sheet,
        character_class=character_class,
        defaults={"level": level, "is_primary": True},
    )
    recompute_max_health_with_threads(sheet)
    return ccl
