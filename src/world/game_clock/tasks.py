"""Periodic task definitions for the game clock scheduler."""

from __future__ import annotations

from datetime import timedelta
import logging

from django.db import models

from world.game_clock.task_registry import (
    CronDefinition,
    register_task,
)

logger = logging.getLogger("world.game_clock.tasks")


def weekly_rollover_task() -> None:
    """Unified weekly rollover: advance GameWeek then run all weekly processors.

    This is the single orchestrator for all weekly systems. It:
    1. Advances the GameWeek (closes current, creates next)
    2. Processes votes → XP for the closed week
    3. Generates new random scene targets
    4. Processes skill development audit + rust
    5. Resets journal weekly XP trackers
    6. Resets relationship weekly counters
    7. Applies weekly AP regeneration

    Individual weekly tasks are kept registered as fallbacks but this
    orchestrator is the primary entry point.
    """
    from world.game_clock.week_services import advance_game_week

    try:
        new_week = advance_game_week()
    except Exception:
        logger.exception("Failed to advance game week")
        return

    logger.info("Weekly rollover: advanced to %s", new_week)

    # Process each weekly system, catching errors individually so one
    # failure doesn't block the others.
    processors = [
        ("vote XP", _run_vote_processing),
        ("random scene generation", _run_random_scene_generation),
        ("skill development", _run_skill_development),
        ("journal weekly reset", batch_journal_weekly_reset),
        ("relationship weekly reset", batch_relationship_weekly_reset),
        ("AP weekly regen", batch_ap_weekly_regen),
    ]

    for name, processor in processors:
        try:
            processor()
            logger.info("Weekly rollover: %s complete", name)
        except Exception:
            logger.exception("Weekly rollover: %s failed", name)


def _run_vote_processing() -> None:
    from world.progression.services.vote_processing import weekly_vote_processing_task

    weekly_vote_processing_task()


def _run_random_scene_generation() -> None:
    from world.progression.services.random_scene import weekly_random_scene_generation_task

    weekly_random_scene_generation_task()


def _run_skill_development() -> None:
    from world.progression.services.skill_development import weekly_skill_development_task

    weekly_skill_development_task()


def _fetch_ap_modifier_map(
    target_names: list[str],
) -> tuple[dict[int, dict[int, int]], dict[str, int]]:
    """Fetch AP ModifierTarget instances by name and batch-aggregate their values.

    Uses ModifierTarget.objects.get() for SharedMemoryModel cache hits.
    Returns (modifier_lookup, target_pk_map) where:
      - modifier_lookup: {object_db_id: {target_pk: total_value}}
      - target_pk_map: {target_name: target_pk}
    Returns empty dicts if any target doesn't exist (no modifiers configured yet).
    """
    from world.mechanics.models import CharacterModifier, ModifierTarget

    targets: list[ModifierTarget] = []
    target_pk_map: dict[str, int] = {}
    for name in target_names:
        try:
            target = ModifierTarget.objects.get(name=name)
        except ModifierTarget.DoesNotExist:
            return {}, {}
        targets.append(target)
        target_pk_map[name] = target.pk

    mod_lookup = CharacterModifier.objects.totals_by_character_for_targets(targets)
    return mod_lookup, target_pk_map


def _apply_ap_regen(regen_target_name: str, base_regen: int) -> int:
    """Shared batch regen logic for daily and weekly AP regeneration.

    Fetches all pools, computes per-character effective regen/max with modifiers,
    and bulk-updates in 3 queries total. Returns the number of pools updated.
    """
    from world.action_points.models import ActionPointPool

    pools = list(ActionPointPool.objects.all())
    if not pools:
        return 0

    mod_lookup, pks = _fetch_ap_modifier_map([regen_target_name, "ap_maximum"])
    regen_pk = pks.get(regen_target_name)
    max_pk = pks.get("ap_maximum")

    to_update: list[ActionPointPool] = []
    for pool in pools:
        mods = mod_lookup.get(pool.character_id, {})
        effective_regen = max(0, base_regen + (mods.get(regen_pk, 0) if regen_pk else 0))
        effective_max = max(1, pool.maximum + (mods.get(max_pk, 0) if max_pk else 0))

        if pool.current >= effective_max or effective_regen == 0:
            continue

        pool.current = min(effective_max, pool.current + effective_regen)
        to_update.append(pool)

    if to_update:
        ActionPointPool.objects.bulk_update(to_update, ["current"], batch_size=500)
    return len(to_update)


def batch_ap_daily_regen() -> None:
    """Apply daily AP regen to all character pools.

    Note: per-pool ``last_daily_regen`` is updated separately from the batch
    bulk_update. The scheduler's ``ScheduledTaskRecord.last_run_at`` is the
    authoritative timing record; the pool-level timestamp is for admin display
    only and is set by the model-level ``apply_daily_regen()`` method.
    """
    from world.action_points.models import ActionPointConfig

    base_regen = ActionPointConfig.get_daily_regen()
    count = _apply_ap_regen("ap_daily_regen", base_regen)
    logger.info("AP daily regen: %d pools regenerated", count)


def batch_ap_weekly_regen() -> None:
    """Apply weekly AP regen to all character pools.

    Weekly timing is tracked by the scheduler's ``ScheduledTaskRecord``;
    there is no per-pool weekly timestamp (unlike ``last_daily_regen`` which
    exists for admin display of daily regen history).
    """
    from world.action_points.models import ActionPointConfig

    base_regen = ActionPointConfig.get_weekly_regen()
    count = _apply_ap_regen("ap_weekly_regen", base_regen)
    logger.info("AP weekly regen: %d pools regenerated", count)


def batch_journal_weekly_reset() -> None:
    """Reset stale weekly journal XP trackers for non-current game weeks."""
    from world.game_clock.week_services import get_current_game_week
    from world.journals.models import WeeklyJournalXP

    current_week = get_current_game_week()
    count = (
        WeeklyJournalXP.objects.exclude(game_week=current_week)
        .filter(
            models.Q(posts_this_week__gt=0)
            | models.Q(praised_this_week=True)
            | models.Q(was_praised_this_week=True)
            | models.Q(retorted_this_week=True)
            | models.Q(was_retorted_this_week=True),
        )
        .update(
            posts_this_week=0,
            praised_this_week=False,
            was_praised_this_week=False,
            retorted_this_week=False,
            was_retorted_this_week=False,
            game_week=current_week,
        )
    )
    logger.info("Journal weekly reset: %d trackers reset", count)


def batch_relationship_weekly_reset() -> None:
    """Reset stale weekly relationship counters for non-current game weeks."""
    from world.game_clock.week_services import get_current_game_week
    from world.relationships.models import CharacterRelationship

    current_week = get_current_game_week()
    count = (
        CharacterRelationship.objects.exclude(game_week=current_week)
        .filter(
            models.Q(developments_this_week__gt=0) | models.Q(changes_this_week__gt=0),
        )
        .update(
            developments_this_week=0,
            changes_this_week=0,
            game_week=current_week,
        )
    )
    logger.info("Relationship weekly reset: %d relationships reset", count)


def batch_form_expiration_cleanup() -> None:
    """Delete expired real-time temporary form changes."""
    from django.utils import timezone

    from world.forms.models import DurationType, TemporaryFormChange

    count, _ = TemporaryFormChange.objects.filter(
        duration_type=DurationType.REAL_TIME,
        expires_at__lt=timezone.now(),
    ).delete()
    logger.info("Form expiration cleanup: %d expired changes deleted", count)


def batch_condition_expiration_cleanup() -> None:
    """Delete expired time-based conditions."""
    from django.utils import timezone

    from world.conditions.models import ConditionInstance

    count, _ = ConditionInstance.objects.filter(
        expires_at__lt=timezone.now(),
    ).delete()
    logger.info("Condition expiration cleanup: %d expired conditions deleted", count)


def register_all_tasks() -> None:
    """Register all periodic tasks with the scheduler."""
    register_task(
        CronDefinition(
            task_key="ap.daily_regen",
            callable=batch_ap_daily_regen,
            interval=timedelta(hours=24),
            description="Apply daily AP regeneration.",
        )
    )
    register_task(
        CronDefinition(
            task_key="ap.weekly_regen",
            callable=batch_ap_weekly_regen,
            interval=timedelta(days=7),
            description="Apply weekly AP regeneration.",
        )
    )
    register_task(
        CronDefinition(
            task_key="journals.weekly_reset",
            callable=batch_journal_weekly_reset,
            interval=timedelta(hours=24),
            description="Batch-reset stale weekly journal XP trackers.",
        )
    )
    register_task(
        CronDefinition(
            task_key="relationships.weekly_reset",
            callable=batch_relationship_weekly_reset,
            interval=timedelta(hours=24),
            description="Reset stale weekly relationship counters.",
        )
    )
    register_task(
        CronDefinition(
            task_key="forms.expiration_cleanup",
            callable=batch_form_expiration_cleanup,
            interval=timedelta(hours=1),
            description="Delete expired real-time temporary form changes.",
        )
    )
    register_task(
        CronDefinition(
            task_key="conditions.expiration_cleanup",
            callable=batch_condition_expiration_cleanup,
            interval=timedelta(hours=1),
            description="Delete expired time-based conditions.",
        )
    )
    from world.fatigue.tasks import fatigue_dawn_reset_task

    register_task(
        CronDefinition(
            task_key="fatigue.dawn_reset",
            callable=fatigue_dawn_reset_task,
            interval=timedelta(hours=8),
            description="Reset fatigue pools at IC dawn.",
        )
    )

    from world.combat.tasks import check_and_resolve_timed_encounters

    register_task(
        CronDefinition(
            task_key="combat.timer_check",
            callable=check_and_resolve_timed_encounters,
            interval=timedelta(seconds=30),
            description="Auto-resolve expired timed combat rounds.",
        )
    )

    from world.conditions.services import decay_all_conditions_tick
    from world.magic.services.anima import anima_regen_tick
    from world.magic.services.gain import resonance_daily_tick, resonance_weekly_settlement_tick

    register_task(
        CronDefinition(
            task_key="magic.anima_regen_daily",
            callable=anima_regen_tick,
            interval=timedelta(hours=24),
            description=(
                "Daily anima pool regeneration (skips engaged characters and "
                "characters whose active condition stages carry blocks_anima_regen)."
            ),
        )
    )
    register_task(
        CronDefinition(
            task_key="conditions.decay_daily",
            callable=decay_all_conditions_tick,
            interval=timedelta(hours=24),
            description="Passive decay for conditions with passive_decay_per_day > 0.",
        )
    )
    register_task(
        CronDefinition(
            task_key="magic.resonance_daily",
            callable=resonance_daily_tick,
            interval=timedelta(hours=24),
            description="Daily resonance trickle (residence + outfit stub).",
        )
    )
    register_task(
        CronDefinition(
            task_key="magic.resonance_weekly_settlement",
            callable=resonance_weekly_settlement_tick,
            interval=timedelta(days=7),
            description=(
                "Weekly pose-endorsement settlement. Idempotent — only sheets with "
                "unsettled endorsements are processed."
            ),
        )
    )

    # Unified weekly rollover — orchestrates all weekly systems in sequence.
    # Advances the GameWeek, then processes votes, random scenes, skills,
    # journals, relationships, and AP regen.
    register_task(
        CronDefinition(
            task_key="weekly_rollover",
            callable=weekly_rollover_task,
            interval=timedelta(days=7),
            description="Weekly rollover: advance GameWeek and process all weekly systems.",
        )
    )
