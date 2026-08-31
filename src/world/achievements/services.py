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
    Discovery,
    PersonaTitle,
    StatDefinition,
    StatTracker,
)
from world.achievements.types import AchievementGrantResult

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.societies.models import LegendEntry

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


def increment_stat_for_group(
    character_sheets: list[CharacterSheet], stat: StatDefinition, amount: int = 1
) -> None:
    """
    Increment a stat for several sheets as one simultaneous group moment.

    A party winning an encounter or both halves of a reciprocated
    relationship are genuinely simultaneous: each sheet's tracker updates
    atomically (mirrors ``increment_stat``'s F() + cache update), with the
    per-sheet achievement check deferred, then ONE group evaluation runs for
    ``(character_sheets, stat)``. Any achievement that multiple sheets cross
    on this increment grants with all crossing sheets in a single
    ``grant_achievement`` call, so a first-ever Discovery is shared instead
    of going solely to whichever sheet a per-sheet loop happened to process
    first. A sheet that does not cross this increment (e.g. one party member
    one win short of the threshold) is simply not in the crossing set --
    it earns the achievement solo, non-shared, on a later increment.
    """
    for sheet in character_sheets:
        sheet.stats.increment(stat, amount, check_achievements=False)
    _check_achievements_for_group(character_sheets, stat)


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
) -> AchievementGrantResult:
    """
    Grant an achievement to one or more characters simultaneously.

    If no CharacterAchievement exists for this achievement yet, creates a
    Discovery and links all characters as co-discoverers via their tenures
    (``discovered_by_tenure`` primary + ``shared_with_tenures`` shared).

    After commit, notifies the stories reactivity service so any active
    stories with ACHIEVEMENT_HELD beats for this achievement are
    re-evaluated (and flip SUCCESS when the requirement is met).

    Ineligible sheets (see ``can_earn_achievements``) are dropped; if none
    remain, returns an empty result and no Discovery is created.
    """
    character_sheets = [s for s in character_sheets if can_earn_achievements(s)]
    if not character_sheets:
        return AchievementGrantResult(character_achievements=[], created_discovery=None)

    from world.stories.services.reactivity import on_achievement_earned  # noqa: PLC0415

    with transaction.atomic():
        is_first_discovery = not CharacterAchievement.objects.filter(
            achievement=achievement
        ).exists()

        discovery = None
        if is_first_discovery:
            # The Discovery slot goes to the first sheet in the list. For a
            # sequential earn that is the triggering sheet and the FK is meaningful;
            # for a simultaneous party grant it is bookkeeping -- the FK is NOT NULL
            # and has to point somewhere, and #3063 ruled the split invisible, so no
            # caller need order its list to win the slot and no reader may treat it
            # as a privilege (#3319). can_earn_achievements already filtered out
            # sheets with no current tenure above, so this is guaranteed to resolve.
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
                defaults={"earned_by_tenure": earning_tenure},
            )
            results.append(char_achievement)
            if created:
                newly_earned.append(sheet)

    # Apply rewards + fire the reactivity hook per newly-earned sheet (once per earn).
    for sheet in newly_earned:
        apply_achievement_rewards(sheet, achievement)
        on_achievement_earned(sheet, achievement)

    return AchievementGrantResult(character_achievements=results, created_discovery=discovery)


def _check_achievements(character_sheet: CharacterSheet, stat: StatDefinition) -> None:
    """
    Find active, unearned achievements with requirements on the given stat
    and grant any whose requirements are fully met for this one sheet.

    Thin wrapper into the group evaluator (see ``_check_achievements_for_group``)
    with a one-element sheet list -- there is only one evaluator, no parallel
    single-sheet copy of the requirement/prerequisite/convergence logic.
    """
    _check_achievements_for_group([character_sheet], stat)


def _check_achievements_for_group(
    character_sheets: list[CharacterSheet], stat: StatDefinition
) -> None:
    """
    Group achievement evaluator for a stat increment shared by one or more sheets.

    Filters to sheets that pass ``can_earn_achievements``, then batch-fetches
    every eligible sheet's earned-achievement id set and stat-value dict with
    two ``character_sheet__in`` queries (no per-sheet queries in a loop).
    Candidates are active achievements with a requirement on ``stat``. For
    each candidate, the crossing set is every sheet (in caller order) whose
    requirements are met now AND who does not already hold the achievement;
    ``grant_achievement`` is called ONCE per achievement with that crossing
    set, so the first eligible crossing sheet takes the primary Discovery
    slot exactly as ``grant_achievement`` documents.

    A convergence loop re-passes for prerequisite chains: if tier2's
    prerequisite is tier1 and a sheet crosses tier1 on this pass, the
    in-memory earned set updates so tier2's prerequisite check sees tier1 as
    earned on the next pass -- regardless of the candidate queryset's
    iteration order.
    """
    eligible_sheets = [s for s in character_sheets if can_earn_achievements(s)]
    if not eligible_sheets:
        return

    candidates = list(
        Achievement.objects.filter(is_active=True, requirements__stat=stat).distinct()
    )
    if not candidates:
        return

    earned_by_sheet = _batch_fetch_earned_ids(eligible_sheets)
    stats_by_sheet = _batch_fetch_stat_values(eligible_sheets)
    requirements_by_achievement = _batch_fetch_requirements(candidates)

    # Iterate until no more grants happen. A single pass is order-dependent for
    # chained achievements: if tier2 (prerequisite=tier1) is iterated before
    # tier1 in the same call, tier2's prereq check sees no tier1 yet and skips.
    # The convergence loop guarantees the full chain grants regardless of the
    # queryset's iteration order, updating earned_by_sheet in memory between
    # passes so a sheet that crosses tier1 this pass can cross tier2 next pass.
    pending = candidates
    while pending:
        granted_this_pass = []
        for achievement in pending:
            crossing_sheets = _crossing_sheets(
                achievement,
                eligible_sheets,
                earned_by_sheet,
                stats_by_sheet,
                requirements_by_achievement[achievement.pk],
            )
            if crossing_sheets:
                grant_achievement(achievement, crossing_sheets)
                granted_this_pass.append(achievement)
                for sheet in crossing_sheets:
                    earned_by_sheet[sheet.pk].add(achievement.pk)
        if not granted_this_pass:
            break
        pending = [a for a in pending if a not in granted_this_pass]


def _batch_fetch_earned_ids(sheets: list[CharacterSheet]) -> dict[int, set[int]]:
    """Per-sheet earned-achievement id sets for ``sheets``, one query, no loop."""
    earned_by_sheet: dict[int, set[int]] = {s.pk: set() for s in sheets}
    for sheet_id, achievement_id in CharacterAchievement.objects.filter(
        character_sheet__in=sheets
    ).values_list("character_sheet_id", "achievement_id"):
        earned_by_sheet[sheet_id].add(achievement_id)
    return earned_by_sheet


def _batch_fetch_stat_values(sheets: list[CharacterSheet]) -> dict[int, dict[int, int]]:
    """Per-sheet stat-value dicts (sheet_id -> {stat_id: value}) for ``sheets``, one query."""
    stats_by_sheet: dict[int, dict[int, int]] = {s.pk: {} for s in sheets}
    for sheet_id, stat_id, value in StatTracker.objects.filter(
        character_sheet__in=sheets
    ).values_list("character_sheet_id", "stat_id", "value"):
        stats_by_sheet[sheet_id][stat_id] = value
    return stats_by_sheet


def _batch_fetch_requirements(
    achievements: list[Achievement],
) -> dict[int, list[AchievementStatRequirement]]:
    """Per-achievement requirement rows for ``achievements``, one query, no loop."""
    requirements_by_achievement: dict[int, list[AchievementStatRequirement]] = {
        a.pk: [] for a in achievements
    }
    for req in AchievementStatRequirement.objects.filter(achievement__in=achievements):
        requirements_by_achievement[req.achievement_id].append(req)
    return requirements_by_achievement


def _crossing_sheets(
    achievement: Achievement,
    eligible_sheets: list[CharacterSheet],
    earned_by_sheet: dict[int, set[int]],
    stats_by_sheet: dict[int, dict[int, int]],
    requirements: list[AchievementStatRequirement],
) -> list[CharacterSheet]:
    """Sheets (in caller order) that cross ``achievement`` on this evaluation.

    A sheet crosses when it does not already hold the achievement and its
    requirements are met against its own stat values.
    """
    return [
        sheet
        for sheet in eligible_sheets
        if achievement.pk not in earned_by_sheet[sheet.pk]
        and _achievement_requirements_met(
            achievement, stats_by_sheet[sheet.pk], earned_by_sheet[sheet.pk], requirements
        )
    ]


def _achievement_requirements_met(
    achievement: Achievement,
    stats_dict: dict[int, int],
    earned_ids: set[int],
    requirements: list[AchievementStatRequirement],
) -> bool:
    """
    Check prerequisite chain and all requirements against a stat dict.

    ``stats_dict`` is keyed by stat_id (int) to value (int); ``earned_ids`` is
    the sheet's already-earned achievement id set, used for the prerequisite
    chain check instead of issuing a query here; ``requirements`` is the
    achievement's prefetched AchievementStatRequirement rows.
    Returns False if no requirements exist (never auto-grant empty achievements).
    """
    # Check prerequisite chain
    if achievement.prerequisite_id is not None and achievement.prerequisite_id not in earned_ids:
        return False

    if not requirements:
        return False

    return all(req.is_met(stats_dict.get(req.stat_id, 0)) for req in requirements)


def _achievement_reward_source():
    """The shared ModifierSource for achievement-granted bonus modifiers (get-or-created)."""
    from world.mechanics.models import ModifierSource  # noqa: PLC0415

    source, _ = ModifierSource.objects.get_or_create(achievement_reward=True)
    return source


def _grant_title(character_sheet: CharacterSheet, reward) -> None:
    """Grant an achievement title to the character's PRIMARY persona (#3466).

    Achievements are sheet-level facts about who someone is, so the title belongs to
    their real identity. Using ``active_persona`` here would stamp an achievement onto
    whatever disguise happened to be worn when a stat ticked over.
    """
    PersonaTitle.objects.get_or_create(persona=character_sheet.primary_persona, reward=reward)


def maybe_grant_deed_title(deed: LegendEntry) -> PersonaTitle | None:
    """Mint a title when a deed crosses its station's threshold (#3466).

    The title's text is the deed's own name, so whoever established the deed named it.
    It lands on ``deed.persona`` - the face that did it - which is what keeps an honor
    from ever outing anyone.

    Raises ``LegendLevelCalibration.DoesNotExist`` when the station has no authored row.
    That is deliberate: see the model's docstring.
    """
    from world.societies.models import LegendLevelCalibration  # noqa: PLC0415

    calibration = LegendLevelCalibration.objects.get(level=deed.earned_at_level)
    if deed.base_value < calibration.deed_title_threshold:
        return None
    title, _ = PersonaTitle.objects.get_or_create(persona=deed.persona, legend_entry=deed)
    return title


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
    attach to the *achievement*, not the title: TITLE records a ``PersonaTitle`` (cosmetic), BONUS
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
