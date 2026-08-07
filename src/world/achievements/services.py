"""
Achievement service functions.

Core integration point for the achievements system. Other apps call
increment_stat() to record actions; the engine evaluates requirements
and awards achievements when thresholds are met.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from world.achievements.constants import RewardType
from world.achievements.models import (
    Achievement,
    AchievementStatRequirement,
    CharacterAchievement,
    CharacterTitle,
    Discovery,
    StatDefinition,
    StatTracker,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

logger = logging.getLogger(__name__)


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


def can_earn_achievements(character_sheet: CharacterSheet) -> bool:
    """Whether ``character_sheet`` may earn achievements at all (#3024).

    Requires a current, non-staff RosterTenure: the character must be piloted
    by a regular player right now. A sheet mid-character-creation (no
    RosterEntry yet), a GM-created sheet sitting untenured on the Available
    roster, a true NPC, or a staff-piloted sheet never earns a
    CharacterAchievement, never claims a first-ever Discovery, never receives
    rewards, and never fires the stories reactivity hook. Enforced inside
    ``grant_achievement`` so every caller inherits it (extends the #2899
    ceremony rule; see ADR-0202).
    """
    from core_management.permissions import is_staff_observer  # noqa: PLC0415

    roster_entry = character_sheet.roster_entry_or_none
    tenure = roster_entry.current_tenure if roster_entry is not None else None
    if tenure is None:
        return False
    return not is_staff_observer(tenure.player_data.account)


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

    Ineligible sheets (see ``can_earn_achievements``) are dropped; if none
    remain, returns ``[]`` and no Discovery is created.
    """
    character_sheets = [s for s in character_sheets if can_earn_achievements(s)]
    if not character_sheets:
        return []

    from world.stories.services.reactivity import on_achievement_earned  # noqa: PLC0415

    with transaction.atomic():
        is_first_discovery = not CharacterAchievement.objects.filter(
            achievement=achievement
        ).exists()

        discovery = None
        if is_first_discovery:
            # The Discovery slot goes to the first (triggering) sheet in the list --
            # callers order this deliberately for party grants. can_earn_achievements
            # already filtered out sheets with no current tenure above, so this is
            # guaranteed to resolve.
            discovering_sheet = character_sheets[0]
            discovering_tenure = discovering_sheet.roster_entry_or_none.current_tenure
            discovery = Discovery.objects.create(
                achievement=achievement, discovered_by_tenure=discovering_tenure
            )
            # Simultaneous co-discoverers (a party/covenant finding it together)
            # share the credit via the M2M; the primary FK stays the triggering
            # tenure (#3055 ruling: required FK + shared set, not per-tenure rows).
            co_tenures = [s.roster_entry_or_none.current_tenure for s in character_sheets[1:]]
            if co_tenures:
                discovery.shared_with_tenures.add(*co_tenures)

        results: list[CharacterAchievement] = []
        newly_earned: list[CharacterSheet] = []
        for sheet in character_sheets:
            # can_earn_achievements already guarantees a current tenure exists.
            earning_tenure = sheet.roster_entry_or_none.current_tenure
            char_achievement, created = CharacterAchievement.objects.get_or_create(
                character_sheet=sheet,
                achievement=achievement,
                defaults={"discovery": discovery, "earned_by_tenure": earning_tenure},
            )
            results.append(char_achievement)
            if created:
                newly_earned.append(sheet)

    # Apply rewards + fire the reactivity hook per newly-earned sheet (once per earn).
    for sheet in newly_earned:
        apply_achievement_rewards(sheet, achievement)
        on_achievement_earned(sheet, achievement)

    return results


def _check_achievements(character_sheet: CharacterSheet, stat: StatDefinition) -> None:
    """
    Find active, unearned achievements with requirements on the given stat
    and grant any whose requirements are fully met.
    """
    if not can_earn_achievements(character_sheet):
        return

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

    requirements = list(AchievementStatRequirement.objects.filter(achievement=achievement))

    if not requirements:
        return False

    return all(req.is_met(stats_dict.get(req.stat_id, 0)) for req in requirements)


def _achievement_reward_source():
    """The shared ModifierSource for achievement-granted bonus modifiers (get-or-created)."""
    from world.mechanics.models import ModifierSource  # noqa: PLC0415

    source, _ = ModifierSource.objects.get_or_create(achievement_reward=True)
    return source


def _grant_title(character_sheet: CharacterSheet, reward) -> None:
    """Record an earned title (idempotent via the unique (sheet, reward) constraint)."""
    CharacterTitle.objects.get_or_create(character_sheet=character_sheet, reward=reward)


def _grant_bonus(character_sheet: CharacterSheet, reward, reward_value: str) -> None:
    """Materialize a BONUS reward as a CharacterModifier on the reward's target (e.g. +5 allure).

    Read by ``get_modifier_total`` like any other modifier (the achievement source is a recognised
    non-distinction source, counted as a flat addend).
    """
    from world.mechanics.models import CharacterModifier  # noqa: PLC0415

    if reward.modifier_target_id is None:
        return
    try:
        value = int(reward_value)
    except (TypeError, ValueError):
        return
    if not value:
        return
    CharacterModifier.objects.create(
        character=character_sheet,
        source=_achievement_reward_source(),
        target=reward.modifier_target,
        value=value,
    )


def _grant_prestige(character_sheet: CharacterSheet, reward_value: str) -> None:
    """Award flat prestige (to the primary persona) for a PRESTIGE reward."""
    from world.societies.renown import award_deed_prestige  # noqa: PLC0415

    persona = character_sheet.primary_persona
    if persona is None:
        return
    try:
        amount = int(reward_value)
    except (TypeError, ValueError):
        return
    award_deed_prestige(persona, amount)


def _grant_distinction(character_sheet: CharacterSheet, reward, reward_value: str) -> None:
    """Grant/rank-up a DISTINCTION reward through the shared acquisition seam (#2037).

    ``reward_value`` optionally encodes an explicit rank: a valid positive int sets/raises to
    that rank; blank, garbage, or non-positive (e.g. "-1", "0") parses as ``rank=None`` (advance
    one step) — deliberately NOT a no-op like ``_grant_bonus``'s parse-or-skip, since a
    DISTINCTION reward with no usable rank should still grant/rank-up the linked distinction.
    A non-positive int must NOT reach ``grant_distinction`` unchanged: ``CharacterDistinction.rank``
    is a ``PositiveIntegerField``, so a raw ``rank=-1`` on a new grant raises an uncaught
    ``IntegrityError`` that rolls back the entire ``grant_achievement`` transaction — including
    every sibling reward — on every re-trigger.

    A mutual/variant exclusion conflict (``DistinctionExclusionError``) is logged and skipped —
    one reward's conflict must never crash the surrounding achievement-award flow.
    """
    from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
    from world.distinctions.services import grant_distinction  # noqa: PLC0415
    from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415

    if reward.distinction_id is None:
        return
    try:
        rank = int(reward_value)
    except (TypeError, ValueError):
        rank = None
    if rank is not None and rank <= 0:
        # Non-positive parses (e.g. a staff-authored "-1") are unusable as an explicit
        # rank -- treat them the same as garbage input and advance one step instead of
        # letting a negative/zero rank reach grant_distinction (#2037 review fold-in).
        # This is the trusted-authored-source fallback (advance-one), NOT the reject
        # discipline _coerce_positive_int uses for player-facing GM input.
        rank = None
    try:
        grant_distinction(
            character_sheet,
            reward.distinction,
            origin=DistinctionOrigin.ACHIEVEMENT_AUTO_GRANT,
            rank=rank,
            source_description=f"Achievement reward: {reward.name}",
        )
    except DistinctionExclusionError:
        logger.warning(
            "Achievement reward %s: distinction grant skipped for sheet %s (exclusion conflict)",
            reward.key,
            character_sheet.pk,
        )


def apply_achievement_rewards(character_sheet: CharacterSheet, achievement: Achievement) -> None:
    """Apply an achievement's rewards to a character — title / bonus / prestige / distinction
    (#1522, #2037).

    Called once per newly-earned (sheet, achievement) by ``grant_achievement``. Mechanical rewards
    attach to the *achievement*, not the title: TITLE records a ``CharacterTitle`` (cosmetic), BONUS
    materializes a ``CharacterModifier`` on the reward's target, PRESTIGE bumps the persona's
    deed-prestige, DISTINCTION grants/ranks-up the linked Distinction via the shared
    ``grant_distinction`` seam. COSMETIC is a no-op until that system lands. Cross-app deps are
    lazy-imported so ``achievements`` stays low-coupled.
    """
    for achievement_reward in achievement.cached_rewards:
        reward = achievement_reward.reward
        value = achievement_reward.reward_value
        if reward.reward_type == RewardType.TITLE:
            _grant_title(character_sheet, reward)
        elif reward.reward_type == RewardType.BONUS:
            _grant_bonus(character_sheet, reward, value)
        elif reward.reward_type == RewardType.PRESTIGE:
            _grant_prestige(character_sheet, value)
        elif reward.reward_type == RewardType.DISTINCTION:
            _grant_distinction(character_sheet, reward, value)
