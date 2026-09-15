"""Periodic task definitions for the scenes app."""

from __future__ import annotations

from datetime import timedelta
import logging

from django.utils import timezone

from world.game_clock.task_registry import CronDefinition, CronPhase, FrequencyType, register_task
from world.scenes.block_services import finalize_expired_blocks
from world.scenes.models import PoseSubmission

logger = logging.getLogger("world.scenes.tasks")

_POSE_SUBMISSION_RETENTION = timedelta(hours=24)


def block_finalize_task() -> None:
    """Finalize blocks whose lift grace period has elapsed (#1278).

    A lifted block stays active until ``pending_removal_at`` (set to a future cron tick), so a
    player can't lift → snipe → re-block. This sweep removes the ones whose grace window has now
    passed.
    """
    removed = finalize_expired_blocks(now=timezone.now())
    logger.info("Block finalize: %d lifted blocks removed", removed)


def pose_submission_cleanup_task() -> None:
    """Cron entry: prune PoseSubmission idempotency-ledger rows past 24h retention (#3760)."""
    cutoff = timezone.now() - _POSE_SUBMISSION_RETENTION
    deleted, _ = PoseSubmission.objects.filter(created_at__lt=cutoff).delete()
    logger.info("Pose submission cleanup: pruned %d expired ledger row(s)", deleted)


def register_all_tasks() -> None:
    """Register scenes' periodic tasks with the game-clock scheduler."""
    register_task(
        CronDefinition(
            task_key="scenes.pose_submission_cleanup",
            callable=pose_submission_cleanup_task,
            interval=timedelta(hours=1),
            frequency_type=FrequencyType.REAL,
            phase=CronPhase.CLEANUP,
            description="Prune PoseSubmission idempotency-ledger rows past 24h retention (#3760).",
        )
    )
