"""Periodic task definitions for missives (#3289)."""

from __future__ import annotations

from datetime import timedelta

from world.game_clock.task_registry import CronDefinition, FrequencyType, register_task


def deliver_task() -> None:
    """Cron entry point: announce missives that have come due."""
    from world.messengers.services import deliver_due_missives  # noqa: PLC0415

    deliver_due_missives()


def register_all_tasks() -> None:
    """Register the missive arrival sweep with the game-clock scheduler.

    Availability itself is lazy (a missive is readable once ``available_at`` passes); this
    sweep only sends the arrival push and re-checks blocks placed while it travelled.
    """
    register_task(
        CronDefinition(
            task_key="missives.deliver",
            callable=deliver_task,
            interval=timedelta(minutes=5),
            frequency_type=FrequencyType.REAL,
            description="Push arrival notices for missives that have come due (#3289).",
        )
    )
