"""Periodic task definitions for the game clock scheduler."""

from __future__ import annotations

from datetime import timedelta
import logging

from django.db.models import Sum

from world.game_clock.task_registry import (
    TaskDefinition,
    register_task,
)

logger = logging.getLogger("world.game_clock.tasks")


def _fetch_ap_modifier_lookup(target_names: list[str]) -> dict[int, dict[str, int]]:
    """Batch-fetch AP modifier totals grouped by character ObjectDB id.

    Returns {object_db_id: {target_name: total_value}}.
    Single query regardless of character count.
    """
    from world.mechanics.models import CharacterModifier

    rows = (
        CharacterModifier.objects.filter(
            source__distinction_effect__target__name__in=target_names,
        )
        .values("character__character_id", "source__distinction_effect__target__name")
        .annotate(total=Sum("value"))
    )

    lookup: dict[int, dict[str, int]] = {}
    for row in rows:
        obj_id = row["character__character_id"]
        target = row["source__distinction_effect__target__name"]
        lookup.setdefault(obj_id, {})[target] = row["total"]
    return lookup


def batch_ap_daily_regen() -> None:
    """Apply daily AP regen to all character pools.

    Uses batch-fetch + Python computation + bulk_update (3 queries total).
    Includes per-character modifier bonuses from distinctions.
    """
    from django.utils import timezone

    from world.action_points.models import ActionPointConfig, ActionPointPool

    base_regen = ActionPointConfig.get_daily_regen()
    now = timezone.now()

    pools = list(ActionPointPool.objects.all())
    if not pools:
        return

    mod_lookup = _fetch_ap_modifier_lookup(["ap_daily_regen", "ap_maximum"])

    to_update: list[ActionPointPool] = []
    for pool in pools:
        mods = mod_lookup.get(pool.character_id, {})
        effective_regen = max(0, base_regen + mods.get("ap_daily_regen", 0))
        effective_max = max(1, pool.maximum + mods.get("ap_maximum", 0))

        if pool.current >= effective_max or effective_regen == 0:
            continue

        pool.current = min(effective_max, pool.current + effective_regen)
        pool.last_daily_regen = now
        to_update.append(pool)

    if to_update:
        ActionPointPool.objects.bulk_update(
            to_update, ["current", "last_daily_regen"], batch_size=500
        )
    logger.info("AP daily regen: %d pools regenerated", len(to_update))


def batch_ap_weekly_regen() -> None:
    """Apply weekly AP regen to all character pools.

    Uses batch-fetch + Python computation + bulk_update (3 queries total).
    Includes per-character modifier bonuses from distinctions.
    """
    from world.action_points.models import ActionPointConfig, ActionPointPool

    base_regen = ActionPointConfig.get_weekly_regen()

    pools = list(ActionPointPool.objects.all())
    if not pools:
        return

    mod_lookup = _fetch_ap_modifier_lookup(["ap_weekly_regen", "ap_maximum"])

    to_update: list[ActionPointPool] = []
    for pool in pools:
        mods = mod_lookup.get(pool.character_id, {})
        effective_regen = max(0, base_regen + mods.get("ap_weekly_regen", 0))
        effective_max = max(1, pool.maximum + mods.get("ap_maximum", 0))

        if pool.current >= effective_max or effective_regen == 0:
            continue

        pool.current = min(effective_max, pool.current + effective_regen)
        to_update.append(pool)

    if to_update:
        ActionPointPool.objects.bulk_update(to_update, ["current"], batch_size=500)
    logger.info("AP weekly regen: %d pools regenerated", len(to_update))


def batch_journal_weekly_reset() -> None:
    """Reset stale weekly journal XP trackers."""
    from django.utils import timezone

    from world.journals.models import WeeklyJournalXP

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    count = WeeklyJournalXP.objects.filter(week_reset_at__lt=week_ago).update(
        posts_this_week=0,
        praised_this_week=False,
        was_praised_this_week=False,
        retorted_this_week=False,
        was_retorted_this_week=False,
        week_reset_at=now,
    )
    logger.info("Journal weekly reset: %d trackers reset", count)


def batch_relationship_weekly_reset() -> None:
    """Reset stale weekly relationship counters."""
    from django.db.models import Q
    from django.utils import timezone

    from world.relationships.models import CharacterRelationship

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    count = CharacterRelationship.objects.filter(
        Q(week_reset_at__lt=week_ago) | Q(week_reset_at__isnull=True),
        Q(developments_this_week__gt=0) | Q(changes_this_week__gt=0),
    ).update(
        developments_this_week=0,
        changes_this_week=0,
        week_reset_at=now,
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
        TaskDefinition(
            task_key="ap.daily_regen",
            callable=batch_ap_daily_regen,
            interval=timedelta(hours=24),
            description="Apply daily AP regeneration.",
        )
    )
    register_task(
        TaskDefinition(
            task_key="ap.weekly_regen",
            callable=batch_ap_weekly_regen,
            interval=timedelta(days=7),
            description="Apply weekly AP regeneration.",
        )
    )
    register_task(
        TaskDefinition(
            task_key="journals.weekly_reset",
            callable=batch_journal_weekly_reset,
            interval=timedelta(hours=24),
            description="Batch-reset stale weekly journal XP trackers.",
        )
    )
    register_task(
        TaskDefinition(
            task_key="relationships.weekly_reset",
            callable=batch_relationship_weekly_reset,
            interval=timedelta(hours=24),
            description="Reset stale weekly relationship counters.",
        )
    )
    register_task(
        TaskDefinition(
            task_key="forms.expiration_cleanup",
            callable=batch_form_expiration_cleanup,
            interval=timedelta(hours=1),
            description="Delete expired real-time temporary form changes.",
        )
    )
    register_task(
        TaskDefinition(
            task_key="conditions.expiration_cleanup",
            callable=batch_condition_expiration_cleanup,
            interval=timedelta(hours=1),
            description="Delete expired time-based conditions.",
        )
    )
