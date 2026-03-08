"""
Achievement service functions.

Core integration point for the achievements system. Other apps call
increment_stat() to record actions; the engine evaluates requirements
and awards achievements when thresholds are met.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import F

from world.achievements.constants import ComparisonType
from world.achievements.models import (
    Achievement,
    AchievementRequirement,
    CharacterAchievement,
    Discovery,
    StatTracker,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def get_stat(character_sheet: CharacterSheet, stat_key: str) -> int:
    """Return current value of a stat tracker, 0 if it doesn't exist."""
    try:
        tracker = StatTracker.objects.get(character_sheet=character_sheet, stat_key=stat_key)
        return tracker.value
    except StatTracker.DoesNotExist:
        return 0


def increment_stat(character_sheet: CharacterSheet, stat_key: str, amount: int = 1) -> int:
    """
    Increment a stat tracker (create if needed) and check for achievements.

    Uses F() expression for atomic increment. Returns the new value.
    """
    tracker, created = StatTracker.objects.get_or_create(
        character_sheet=character_sheet,
        stat_key=stat_key,
        defaults={"value": amount},
    )
    if not created:
        StatTracker.objects.filter(pk=tracker.pk).update(value=F("value") + amount)
        tracker.refresh_from_db()

    _check_achievements(character_sheet, stat_key)
    return tracker.value


def grant_achievement(
    achievement: Achievement, character_sheets: list[CharacterSheet]
) -> list[CharacterAchievement]:
    """
    Grant an achievement to one or more characters simultaneously.

    If no CharacterAchievement exists for this achievement yet, creates a
    Discovery and links all characters as co-discoverers.
    """
    with transaction.atomic():
        is_first_discovery = not CharacterAchievement.objects.filter(
            achievement=achievement
        ).exists()

        discovery = None
        if is_first_discovery:
            discovery = Discovery.objects.create(achievement=achievement)

        results: list[CharacterAchievement] = []
        for sheet in character_sheets:
            char_achievement, _ = CharacterAchievement.objects.get_or_create(
                character_sheet=sheet,
                achievement=achievement,
                defaults={"discovery": discovery},
            )
            results.append(char_achievement)

        return results


def _check_achievements(character_sheet: CharacterSheet, stat_key: str) -> None:
    """
    Find active, unearned achievements with requirements on stat_key and
    grant any whose requirements are fully met.
    """
    earned_ids = CharacterAchievement.objects.filter(character_sheet=character_sheet).values_list(
        "achievement_id", flat=True
    )

    candidates = (
        Achievement.objects.filter(
            is_active=True,
            requirements__stat_key=stat_key,
        )
        .exclude(id__in=earned_ids)
        .distinct()
    )

    if not candidates:
        return

    # Batch-fetch all stat values for this character
    stats_dict: dict[str, int] = dict(
        StatTracker.objects.filter(character_sheet=character_sheet).values_list("stat_key", "value")
    )

    for achievement in candidates:
        if _achievement_requirements_met(achievement, stats_dict, character_sheet):
            grant_achievement(achievement, [character_sheet])


def _compare(value: int, threshold: int, comparison: str) -> bool:
    """Simple comparison using ComparisonType."""
    if comparison == ComparisonType.GTE:
        return value >= threshold
    if comparison == ComparisonType.EQ:
        return value == threshold
    if comparison == ComparisonType.LTE:
        return value <= threshold
    return False


def _achievement_requirements_met(
    achievement: Achievement, stats_dict: dict[str, int], character_sheet: CharacterSheet
) -> bool:
    """
    Check prerequisite chain and all requirements against stats dict.

    Returns False if no requirements exist (never auto-grant empty achievements).
    """
    # Check prerequisite chain
    if achievement.prerequisite_id is not None:
        if not CharacterAchievement.objects.filter(
            character_sheet=character_sheet,
            achievement_id=achievement.prerequisite_id,
        ).exists():
            return False

    requirements = list(
        AchievementRequirement.objects.filter(achievement=achievement).values_list(
            "stat_key", "threshold", "comparison", named=True
        )
    )

    if not requirements:
        return False

    return all(
        _compare(stats_dict.get(req.stat_key, 0), req.threshold, req.comparison)
        for req in requirements
    )
