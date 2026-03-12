"""Periodic task definitions for the game clock scheduler."""

from __future__ import annotations

from datetime import timedelta
import logging

from world.game_clock.task_registry import (
    TaskDefinition,
    register_task,
)

logger = logging.getLogger("world.game_clock.tasks")


def batch_ap_daily_regen() -> None:
    """Apply daily AP regen to all character pools.

    Uses a single bulk UPDATE with F() expressions. Revisit when AP modifiers
    are implemented — at that point per-character modifier lookups may require
    falling back to a loop with select_for_update.
    """
    from django.db.models import F
    from django.db.models.functions import Least
    from django.utils import timezone

    from world.action_points.models import ActionPointConfig, ActionPointPool

    regen = ActionPointConfig.get_daily_regen()
    count = ActionPointPool.objects.filter(current__lt=F("maximum")).update(
        current=Least(F("maximum"), F("current") + regen),
        last_daily_regen=timezone.now(),
    )
    logger.info("AP daily regen: %d pools regenerated", count)


def batch_ap_weekly_regen() -> None:
    """Apply weekly AP regen to all character pools.

    Uses a single bulk UPDATE with F() expressions. Revisit when AP modifiers
    are implemented — at that point per-character modifier lookups may require
    falling back to a loop with select_for_update.
    """
    from django.db.models import F
    from django.db.models.functions import Least

    from world.action_points.models import ActionPointConfig, ActionPointPool

    regen = ActionPointConfig.get_weekly_regen()
    count = ActionPointPool.objects.filter(current__lt=F("maximum")).update(
        current=Least(F("maximum"), F("current") + regen),
    )
    logger.info("AP weekly regen: %d pools regenerated", count)


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
