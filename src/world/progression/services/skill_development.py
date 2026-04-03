"""Service functions for awarding development points from skill checks.

When a character performs a check through the fatigue pipeline, qualifying
effort levels earn development points toward the traits used in the check.
Points accumulate in :class:`DevelopmentPoints` and trigger automatic
skill level-ups when cumulative thresholds are crossed.

Also handles weekly skill development processing: audit trail creation for
earned dp and rust application for unused skills.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, cast

from django.db.models import F

from world.classes.models import CharacterClassLevel
from world.fatigue.constants import EffortLevel
from world.progression.constants import (
    DP_BASE_LEVEL,
    DP_COST_MULTIPLIER,
    DP_COST_OFFSET,
    RUST_BASE_AMOUNT,
)
from world.progression.models.rewards import (
    DevelopmentPoints,
    DevelopmentTransaction,
    WeeklySkillUsage,
)
from world.progression.services.voting import get_current_week_start
from world.progression.types import DevelopmentSource, ProgressionReason

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType

logger = logging.getLogger("world.progression.skill_development")

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


def _level_cost(level: int) -> int:
    """Cost to reach the given level from the previous level.

    For level 11: ``(11 - 9) * 100 = 200``.  For levels at or below the
    base CG level (10), cost is 0.
    """
    if level <= DP_BASE_LEVEL:
        return 0
    return (level - DP_COST_OFFSET) * DP_COST_MULTIPLIER


def apply_skill_rust(
    dev_points: DevelopmentPoints,
    character_level: int,
    trait_level: int,
) -> int:
    """Apply weekly rust debt to a single skill's development tracker.

    Rust amount is ``character_level + RUST_BASE_AMOUNT``, capped at the
    dp cost of the skill's current level (i.e. the cost from
    ``current_level - 1`` to ``current_level``). Skills at or below the
    base CG level (10) have no maintenance cost and receive no rust.

    Args:
        dev_points: The :class:`DevelopmentPoints` row for this character+trait.
        character_level: The character's primary class level.
        trait_level: The trait's current value/level.

    Returns:
        The amount of rust debt actually applied (0 for low-level traits).
    """
    if trait_level <= DP_BASE_LEVEL:
        return 0

    rust_amount = character_level + RUST_BASE_AMOUNT
    level_cap = _level_cost(trait_level)
    rust_amount = min(rust_amount, level_cap)

    dev_points.rust_debt = cast(int, dev_points.rust_debt) + rust_amount
    dev_points.save(update_fields=["rust_debt"])
    return rust_amount


def process_weekly_skill_development(week_start: datetime.date) -> None:
    """Process all skill development for a completed week.

    1. For every :class:`WeeklySkillUsage` row for *week_start*, create a
       single :class:`DevelopmentTransaction` audit record per character+trait
       and mark the usage row as processed.
    2. For every :class:`DevelopmentPoints` row whose character+trait does
       **not** have a usage row for this week (and the trait level is above
       the CG base), apply rust debt.

    Args:
        week_start: The Monday of the week to process.
    """
    from world.traits.models import CharacterTraitValue

    # --- Step 1: Audit transactions for earned dp ---
    unprocessed = WeeklySkillUsage.objects.filter(
        week_start=week_start, processed=False
    ).select_related("trait")

    # Collect character+trait pairs that were used this week
    used_pairs: set[tuple[int, int]] = set()
    audit_records: list[DevelopmentTransaction] = []
    usage_pks: list[int] = []

    for usage in unprocessed:
        used_pairs.add((usage.character_id, usage.trait_id))
        usage_pks.append(usage.pk)
        audit_records.append(
            DevelopmentTransaction(
                character_id=usage.character_id,
                trait_id=usage.trait_id,
                source=DevelopmentSource.SCENE,
                amount=usage.points_earned,
                reason=ProgressionReason.SYSTEM_AWARD,
                description=(
                    f"Earned {usage.points_earned} dp from {usage.check_count} "
                    f"skill checks this week"
                ),
            )
        )

    if audit_records:
        DevelopmentTransaction.objects.bulk_create(audit_records)
    if usage_pks:
        WeeklySkillUsage.objects.filter(pk__in=usage_pks).update(processed=True)

    # --- Step 2: Apply rust to unused skills ---
    all_dev_points = DevelopmentPoints.objects.select_related("trait").all()

    # Build a map of character -> their primary class level
    character_ids = {dp.character_id for dp in all_dev_points}
    char_levels: dict[int, int] = {}
    for char_id in character_ids:
        from evennia.objects.models import ObjectDB

        char = ObjectDB.objects.get(pk=char_id)
        char_levels[char_id] = get_character_path_level(char)

    # Build a map of (character_id, trait_id) -> current trait level
    trait_values = CharacterTraitValue.objects.filter(
        character_id__in=character_ids,
    ).values_list("character_id", "trait_id", "value")
    trait_level_map: dict[tuple[int, int], int] = {
        (char_id, trait_id): value for char_id, trait_id, value in trait_values
    }

    rust_transactions: list[DevelopmentTransaction] = []

    for dp in all_dev_points:
        pair = (dp.character_id, dp.trait_id)
        if pair in used_pairs:
            continue

        trait_level = trait_level_map.get(pair, DP_BASE_LEVEL)
        if trait_level <= DP_BASE_LEVEL:
            continue

        char_level = char_levels.get(dp.character_id, 1)
        rust_applied = apply_skill_rust(dp, char_level, trait_level)
        if rust_applied > 0:
            rust_transactions.append(
                DevelopmentTransaction(
                    character_id=dp.character_id,
                    trait_id=dp.trait_id,
                    source=DevelopmentSource.RUST,
                    amount=rust_applied,
                    reason=ProgressionReason.SYSTEM_AWARD,
                    description=(f"Skill rust: {rust_applied} dp debt from inactivity"),
                )
            )

    if rust_transactions:
        DevelopmentTransaction.objects.bulk_create(rust_transactions)

    logger.info(
        "Weekly skill development: %d audit records, %d rust applications for week %s",
        len(audit_records),
        len(rust_transactions),
        week_start,
    )


def weekly_skill_development_task() -> None:
    """Cron wrapper: process skill development for the previous week."""
    today = datetime.datetime.now(tz=datetime.UTC).date()
    previous_week_start = today - datetime.timedelta(days=today.weekday() + 7)
    process_weekly_skill_development(previous_week_start)
