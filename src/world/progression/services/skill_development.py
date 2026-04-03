"""Service functions for awarding development points from skill checks.

When a character performs a check through the fatigue pipeline, qualifying
effort levels earn development points toward the traits used in the check.
Points accumulate in :class:`DevelopmentPoints` and trigger automatic
skill level-ups when cumulative thresholds are crossed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.db.models import F

from world.classes.models import CharacterClassLevel
from world.fatigue.constants import EffortLevel
from world.progression.models.rewards import DevelopmentPoints, WeeklySkillUsage
from world.progression.services.voting import get_current_week_start

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType

# Base dp earned per qualifying check, keyed by effort level.
EFFORT_DEV_BASE: dict[str, int] = {
    EffortLevel.VERY_LOW: 0,
    EffortLevel.LOW: 0,
    EffortLevel.MEDIUM: 10,
    EffortLevel.HIGH: 20,
    EffortLevel.EXTREME: 30,
}


def get_character_path_level(character: ObjectDB) -> int:
    """Return the character's primary class level (or highest, or 1)."""
    primary = CharacterClassLevel.objects.filter(character=character, is_primary=True).first()
    if primary:
        return cast(int, primary.level)

    highest = CharacterClassLevel.objects.filter(character=character).order_by("-level").first()
    if highest:
        return cast(int, highest.level)

    return 1


def calculate_check_dev_points(effort_level: str, path_level: int) -> int:
    """Calculate dp earned from a single check.

    Args:
        effort_level: The :class:`EffortLevel` value for the check.
        path_level: The character's current path/class level.

    Returns:
        Development points earned (may be 0 for low-effort checks).
    """
    base = EFFORT_DEV_BASE.get(effort_level, 0)
    if base == 0:
        return 0
    multiplier = 1 + (path_level // 2)
    return base * multiplier


def award_check_development(
    character: ObjectDB,
    check_type: CheckType,
    effort_level: str | None,
    path_level: int,
) -> list[tuple[str, int, int]]:
    """Award dp to traits used in a check.

    Called by the action pipeline after a check resolves. Updates both the
    :class:`WeeklySkillUsage` tracker (for summaries/rust prevention) and
    the :class:`DevelopmentPoints` accumulator (for level-ups).

    Args:
        character: The character who performed the check.
        check_type: The :class:`CheckType` that was resolved.
        effort_level: The :class:`EffortLevel` value, or ``None`` if no effort.
        path_level: The character's current path/class level.

    Returns:
        List of ``(trait_name, old_level, new_level)`` for each level-up.
    """
    if effort_level is None:
        return []

    dp = calculate_check_dev_points(effort_level, path_level)
    if dp == 0:
        return []

    week_start = get_current_week_start()
    level_ups: list[tuple[str, int, int]] = []

    for check_trait in check_type.traits.select_related("trait").all():
        trait = check_trait.trait

        # Upsert WeeklySkillUsage with atomic F() increments.
        # Try to update first; create only if no row exists yet.
        updated = WeeklySkillUsage.objects.filter(
            character=character,
            trait=trait,
            week_start=week_start,
        ).update(
            points_earned=F("points_earned") + dp,
            check_count=F("check_count") + 1,
        )
        if not updated:
            WeeklySkillUsage.objects.create(
                character=character,
                trait=trait,
                week_start=week_start,
                points_earned=dp,
                check_count=1,
            )

        # Apply dp to the development tracker
        dev_tracker, _created = DevelopmentPoints.objects.get_or_create(
            character=character,
            trait=trait,
        )
        trait_level_ups = dev_tracker.award_points(dp)
        for old_lvl, new_lvl in trait_level_ups:
            level_ups.append((trait.name, old_lvl, new_lvl))

    return level_ups
