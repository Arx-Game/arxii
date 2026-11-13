"""Periodic task definitions for player channels (#3299)."""

from __future__ import annotations

from datetime import timedelta
import logging

from world.channels.services import prune_channel_history
from world.game_clock.task_registry import CronDefinition, CronPhase, FrequencyType, register_task

logger = logging.getLogger("world.channels.tasks")


def prune_history_task() -> None:
    """Cron entry: keep only the newest CHANNEL_HISTORY_CAP messages per channel."""
    deleted = prune_channel_history()
    logger.info("Channel history prune: deleted %d message(s)", deleted)


def register_all_tasks() -> None:
    """Register the channels app's periodic tasks with the game-clock scheduler."""
    register_task(
        CronDefinition(
            task_key="channels.prune_history",
            callable=prune_history_task,
            interval=timedelta(hours=1),
            frequency_type=FrequencyType.REAL,
            phase=CronPhase.CLEANUP,
            description="Prune channel history beyond the per-channel cap (#3299).",
        )
    )
