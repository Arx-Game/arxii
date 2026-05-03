"""
Achievement service functions.

Core integration point for the achievements system. Other apps call
increment_stat() to record actions; the engine evaluates requirements
and awards achievements when thresholds are met.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.achievements.models import (
    Achievement,
    AchievementRequirement,
    CharacterAchievement,
    Discovery,
    StatDefinition,
    StatTracker,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def get_stat(character_sheet: CharacterSheet, stat: StatDefinition) -> int:
    """Return current value of a stat tracker, 0 if it doesn't exist.

    Delegates to the StatHandler on the character sheet for caching.
    """
    return character_sheet.stats.get(stat)


def increment_stat(character_sheet: CharacterSheet, stat: StatDefinition, amount: int = 1) -> int:
    """
    Increment a stat tracker (create if needed) and check for achievements.

    Delegates to the StatHandler on the character sheet for caching and
    atomic DB increment. Returns the new value.
    """
    return character_sheet.stats.increment(stat, amount)


def grant_achievement(
    achievement: Achievement, character_sheets: list[CharacterSheet]
) -> list[CharacterAchievement]:
    """
    Grant an achievement to one or more characters simultaneously.

    If no CharacterAchievement exists for this achievement yet, creates a
    Discovery and links all characters as co-discoverers.

    After commit, notifies the stories reactivity service so any active
    stories with ACHIEVEMENT_HELD beats for this achievement are
    re-evaluated (and flip SUCCESS when the requirement is met).
    """
    from world.stories.services.reactivity import on_achievement_earned  # noqa: PLC0415

    with transaction.atomic():
        is_first_discovery = not CharacterAchievement.objects.filter(
            achievement=achievement
        ).exists()

        discovery = None
        if is_first_discovery:
            discovery = Discovery.objects.create(achievement=achievement)

        results: list[CharacterAchievement] = []
        newly_earned: list[CharacterSheet] = []
        for sheet in character_sheets:
            char_achievement, created = CharacterAchievement.objects.get_or_create(
                character_sheet=sheet,
                achievement=achievement,
                defaults={"discovery": discovery},
            )
            results.append(char_achievement)
            if created:
                newly_earned.append(sheet)

    # Reactivity hook fires per newly-earned sheet. Idempotent — safe on replay.
    for sheet in newly_earned:
        on_achievement_earned(sheet, achievement)

    return results


def _check_achievements(character_sheet: CharacterSheet, stat: StatDefinition) -> None:
    """
    Find active, unearned achievements with requirements on the given stat
    and grant any whose requirements are fully met.
    """
    earned_ids = CharacterAchievement.objects.filter(character_sheet=character_sheet).values_list(
        "achievement_id", flat=True
    )

    candidates = (
        Achievement.objects.filter(
            is_active=True,
            requirements__stat=stat,
        )
        .exclude(id__in=earned_ids)
        .distinct()
    )

    if not candidates:
        return

    # Batch-fetch all stat values for this character, keyed by stat_id
    stats_dict: dict[int, int] = dict(
        StatTracker.objects.filter(character_sheet=character_sheet).values_list("stat_id", "value")
    )

    # Iterate until no more grants happen. A single pass is order-dependent for
    # chained achievements: if tier2 (prerequisite=tier1) is iterated before
    # tier1 in the same call, tier2's prereq check sees no tier1 yet and skips.
    # The convergence loop guarantees the full chain grants regardless of the
    # queryset's iteration order.
    pending = list(candidates)
    while pending:
        granted_this_pass = []
        for achievement in pending:
            if _achievement_requirements_met(achievement, stats_dict, character_sheet):
                grant_achievement(achievement, [character_sheet])
                granted_this_pass.append(achievement)
        if not granted_this_pass:
            break
        pending = [a for a in pending if a not in granted_this_pass]


def _achievement_requirements_met(
    achievement: Achievement, stats_dict: dict[int, int], character_sheet: CharacterSheet
) -> bool:
    """
    Check prerequisite chain and all requirements against stats dict.

    stats_dict is keyed by stat_id (int) to value (int).
    Returns False if no requirements exist (never auto-grant empty achievements).
    """
    # Check prerequisite chain
    if achievement.prerequisite_id is not None:
        if not CharacterAchievement.objects.filter(
            character_sheet=character_sheet,
            achievement_id=achievement.prerequisite_id,
        ).exists():
            return False

    requirements = list(AchievementRequirement.objects.filter(achievement=achievement))

    if not requirements:
        return False

    return all(req.is_met(stats_dict.get(req.stat_id, 0)) for req in requirements)
