"""Periodic task definitions for worship (#4333 slice 3)."""

from __future__ import annotations

from datetime import timedelta

from world.game_clock.task_registry import CronDefinition, register_task


def register_all_tasks() -> None:
    """Register worship's periodic tasks with the game-clock scheduler.

    Held answers: an answer drawn at a pledge's close while the being's worship
    pool was short is sent as a vision once the pool can pay.
    """
    from world.worship.answer_services import deliver_held_answers  # noqa: PLC0415

    register_task(
        CronDefinition(
            task_key="worship.held_answers",
            callable=deliver_held_answers,
            interval=timedelta(hours=24),
            description="Deliver held pledge answers whose being's worship pool can now pay.",
        )
    )
