"""Service functions for awarding development points from skill checks.

When a character performs a check through the fatigue pipeline, qualifying
effort levels earn development points toward the traits used in the check.
Points accumulate in :class:`DevelopmentPoints` and trigger automatic
skill level-ups when cumulative thresholds are crossed.

Also handles weekly skill development processing: audit trail creation for
earned dp and rust application for unused skills.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from django.db import IntegrityError, models as db_models, transaction
from django.db.models import F

from world.classes.models import CharacterClassLevel
from world.game_clock.models import GameWeek
from world.game_clock.week_services import get_current_game_week
from world.progression.constants import (
    DP_BASE_LEVEL,
    DP_COST_MULTIPLIER,
    EFFORT_DEV_BASE,
    PATH_LEVEL_DIVISOR,
    RUST_BASE_AMOUNT,
)
from world.progression.models.rewards import (
    DevelopmentPoints,
    DevelopmentTransaction,
    WeeklySkillUsage,
)
from world.progression.types import DevelopmentSource, ProgressionReason

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType

logger = logging.getLogger("world.progression.skill_development")


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
    multiplier = 1 + (path_level // PATH_LEVEL_DIVISOR)
    return base * multiplier


@transaction.atomic
def award_check_development(
    character_sheet: CharacterSheet,
    check_type: CheckType,
    effort_level: str | None,
    path_level: int,
) -> list[tuple[str, int, int]]:
    """Award dp to traits used in a check.

    Called by the action pipeline after a check resolves. Updates both the
    :class:`WeeklySkillUsage` tracker (for summaries/rust prevention) and
    the :class:`DevelopmentPoints` accumulator (for level-ups).

    Args:
        character_sheet: The character's sheet.
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

    game_week = get_current_game_week()
    level_ups: list[tuple[str, int, int]] = []

    for check_trait in check_type.traits.select_related("trait").all():
        trait = check_trait.trait

        # Upsert WeeklySkillUsage with atomic F() increments.
        # Try to create first; if a concurrent insert wins the race, fall
        # back to an atomic UPDATE with F() expressions.
        try:
            WeeklySkillUsage.objects.create(
                character_sheet=character_sheet,
                trait=trait,
                game_week=game_week,
                points_earned=dp,
                check_count=1,
            )
        except IntegrityError:
            WeeklySkillUsage.objects.filter(
                character_sheet=character_sheet,
                trait=trait,
                game_week=game_week,
            ).update(
                points_earned=F("points_earned") + dp,
                check_count=F("check_count") + 1,
            )

        # Apply dp to the development tracker (lock row to prevent concurrent updates)
        dev_tracker, _created = DevelopmentPoints.objects.select_for_update().get_or_create(
            character_sheet=character_sheet,
            trait=trait,
        )
        trait_level_ups = dev_tracker.award_points(dp)
        for old_lvl, new_lvl in trait_level_ups:
            level_ups.append((trait.name, old_lvl, new_lvl))

    return level_ups


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
    # Cap rust at the cost that was paid to reach the current level from the
    # previous one: (trait_level - DP_BASE_LEVEL) * DP_COST_MULTIPLIER.
    # For level 11 this is 100, for level 15 it is 500.
    max_rust = (trait_level - DP_BASE_LEVEL) * DP_COST_MULTIPLIER
    rust_amount = min(rust_amount, max_rust)

    dev_points.rust_debt = cast(int, dev_points.rust_debt) + rust_amount
    dev_points.save(update_fields=["rust_debt"])
    return rust_amount


def _get_character_levels_batch(character_ids: set[int]) -> dict[int, int]:
    """Batch-fetch character class levels for a set of character IDs.

    Prefers the primary class level; falls back to the highest level.
    Returns 1 for characters with no class levels at all.
    """
    primary_levels = CharacterClassLevel.objects.filter(
        character_id__in=character_ids, is_primary=True
    ).values_list("character_id", "level")
    char_levels: dict[int, int] = dict(primary_levels)

    missing_ids = character_ids - set(char_levels.keys())
    if missing_ids:
        highest = (
            CharacterClassLevel.objects.filter(character_id__in=missing_ids)
            .values("character_id")
            .annotate(max_level=db_models.Max("level"))
        )
        for row in highest:
            char_levels[row["character_id"]] = row["max_level"]

    return char_levels


def _apply_weekly_rust(
    game_week: GameWeek,
    used_pairs: set[tuple[int, int]],
) -> int:
    """Apply rust to unused skills for a given week. Returns the number of rust applications.

    Idempotent: checks for existing RUST transactions referencing the game week
    and skips processing if any are found.
    """
    from world.traits.models import CharacterTraitValue

    # Idempotency guard: skip rust if it was already applied for this week.
    week_marker = f"(week {game_week})"
    already_rusted = DevelopmentTransaction.objects.filter(
        source=DevelopmentSource.RUST,
        description__endswith=week_marker,
    ).exists()
    if already_rusted:
        logger.info(
            "Weekly skill development: rust already applied for %s, skipping.",
            game_week,
        )
        return 0

    # Exclude character+trait pairs that were used this week.
    # NOTE: This builds an OR-chain of Q objects, which scales linearly with the
    # number of used pairs. For large player bases (1000+ active skill usages per
    # week), consider replacing with a subquery or raw SQL NOT IN clause. For MVP
    # scale this is acceptable.
    rust_qs = DevelopmentPoints.objects.select_related("trait").all()
    if used_pairs:
        from django.db.models import Q

        exclusions = Q()
        for sheet_id, trait_id in used_pairs:
            exclusions |= Q(character_sheet_id=sheet_id, trait_id=trait_id)
        rust_qs = rust_qs.exclude(exclusions)

    all_dev_points = list(rust_qs)
    # CharacterSheet PK == ObjectDB PK, so these IDs work for both models
    character_ids = {dp.character_sheet_id for dp in all_dev_points}
    char_levels = _get_character_levels_batch(character_ids)

    # Build a map of (character_sheet_id, trait_id) -> current trait level
    # CharacterTraitValue uses ObjectDB FK but the PK values are identical
    trait_values = CharacterTraitValue.objects.filter(
        character_id__in=character_ids,
    ).values_list("character_id", "trait_id", "value")
    trait_level_map: dict[tuple[int, int], int] = {
        (char_id, trait_id): value for char_id, trait_id, value in trait_values
    }

    rust_transactions: list[DevelopmentTransaction] = []
    for dp in all_dev_points:
        pair = (dp.character_sheet_id, dp.trait_id)
        trait_level = trait_level_map.get(pair, DP_BASE_LEVEL)
        if trait_level <= DP_BASE_LEVEL:
            continue

        char_level = char_levels.get(dp.character_sheet_id, 1)
        rust_applied = apply_skill_rust(dp, char_level, trait_level)
        if rust_applied > 0:
            rust_transactions.append(
                DevelopmentTransaction(
                    character_sheet_id=dp.character_sheet_id,
                    trait_id=dp.trait_id,
                    source=DevelopmentSource.RUST,
                    amount=rust_applied,
                    reason=ProgressionReason.SYSTEM_AWARD,
                    description=(
                        f"Skill rust: {rust_applied} dp debt from inactivity (week {game_week})"
                    ),
                )
            )

    if rust_transactions:
        DevelopmentTransaction.objects.bulk_create(rust_transactions)

    return len(rust_transactions)


def process_weekly_skill_development(game_week: GameWeek) -> None:
    """Process all skill development for a completed week.

    1. For every :class:`WeeklySkillUsage` row for *game_week*, create a
       single :class:`DevelopmentTransaction` audit record per character+trait
       and mark the usage row as processed.
    2. For every :class:`DevelopmentPoints` row whose character+trait does
       **not** have a usage row for this week (and the trait level is above
       the CG base), apply rust debt.

    Args:
        game_week: The GameWeek to process.
    """
    # --- Step 1: Audit transactions for earned dp ---
    unprocessed = WeeklySkillUsage.objects.filter(
        game_week=game_week, processed=False
    ).select_related("trait")

    # Collect character+trait pairs that were used this week
    used_pairs: set[tuple[int, int]] = set()
    audit_records: list[DevelopmentTransaction] = []
    usage_pks: list[int] = []

    for usage in unprocessed:
        used_pairs.add((usage.character_sheet_id, usage.trait_id))
        usage_pks.append(usage.pk)
        audit_records.append(
            DevelopmentTransaction(
                character_sheet_id=usage.character_sheet_id,
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
    rust_count = _apply_weekly_rust(game_week, used_pairs)

    logger.info(
        "Weekly skill development: %d audit records, %d rust applications for %s",
        len(audit_records),
        rust_count,
        game_week,
    )


def weekly_skill_development_task() -> None:
    """Cron wrapper: process skill development for the previous week.

    Looks for the most recent non-current GameWeek (i.e. the one that just ended).
    """
    current = get_current_game_week()
    previous = (
        GameWeek.objects.filter(ended_at__isnull=False)
        .exclude(pk=current.pk)
        .order_by("-started_at")
        .first()
    )
    if previous is None:
        logger.info("No previous game week found; skipping skill development processing.")
        return
    process_weekly_skill_development(previous)
