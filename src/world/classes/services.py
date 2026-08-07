"""Service helpers for the classes app."""

from world.classes.models import CharacterClass, PathStage

#: The single shared placeholder CharacterClass stamped on every character (PC or
#: NPC) until real class selection exists. Originally introduced by
#: world.progression.seeds.seed_durance_officiants (#2121) for seeded Durance
#: officiants; CG finalize and the #2121 select_initial_path recovery seam
#: (world.progression.services.advancement) now stamp it on every PC too (#3038)
#: — advancement only ever reads current_level/Path lineage, never a specific
#: CharacterClass name, so one shared class is the correct generic anchor
#: everywhere a class level is required.
DEFAULT_CHARACTER_CLASS_NAME = "Adventurer"

# (min_level, stage) descending — first whose min_level <= level wins.
_STAGE_THRESHOLDS: list[tuple[int, int]] = [
    (21, PathStage.TRANSCENDENT),
    (16, PathStage.GRAND),
    (11, PathStage.TRUE),
    (6, PathStage.PUISSANT),
    (3, PathStage.POTENTIAL),
    (1, PathStage.PROSPECT),
]


def ensure_default_character_class() -> CharacterClass:
    """Get or create the single shared default CharacterClass (#3038).

    Idempotent via get_or_create; never overwrites a staff-adjusted description
    on an existing row. Callers: the #2121 seeded Durance officiants, CG
    finalize's level-1 stamp, and the #2121 select_initial_path recovery seam
    — see ``DEFAULT_CHARACTER_CLASS_NAME`` for why one shared class is correct
    everywhere.

    Returns:
        The default CharacterClass (created or fetched).
    """
    character_class, _ = CharacterClass.objects.get_or_create(
        name=DEFAULT_CHARACTER_CLASS_NAME,
        defaults={
            "description": "Default class stamped on characters before class selection exists.",
        },
    )
    return character_class


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
    # #3001: anima maximum is level-derived too. No-ops when the sheet has no
    # CharacterAnima row yet (CG stamps the level before the anima seed).
    from world.magic.services.anima import recompute_max_anima  # noqa: PLC0415

    recompute_max_anima(sheet)
    return ccl
